from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from ai_bot.analyzer.result import AnalysisResult
from ai_bot.config import Settings
from ai_bot.db.models import AnalysisRun
from ai_bot.safety import benign_cooldown, cost_guard, dedup
from ai_bot.services.github_client import GitHubClient
from ai_bot.services.log_fetcher import LogFetcher, LogLine
from ai_bot.services.pr_templates import (
    build_benign_alert_proposal_body,
    build_benign_pr_body,
    build_code_bug_issue_body,
    build_code_bug_pr_body,
    build_data_anomaly_issue_body,
    build_infra_issue_body,
    build_insufficient_context_issue_body,
    build_slack_message,
)
from ai_bot.services.repo_manager import RepoManager, RepoManagerError
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.schemas import IncidentEvent

logger = logging.getLogger(__name__)


class Analyzer(Protocol):
    async def analyze(
        self, *, worktree_path, error_class: str, commit_sha: str, log_lines: list[LogLine],
    ) -> AnalysisResult: ...


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession],
        log_fetcher: LogFetcher,
        repo_manager: RepoManager,
        slack: SlackNotifier,
        analyzer: Analyzer,
        github: GitHubClient,
    ) -> None:
        self._settings = settings
        self._session_maker = session_maker
        self._log_fetcher = log_fetcher
        self._repo_manager = repo_manager
        self._slack = slack
        self._analyzer = analyzer
        self._github = github

    async def handle(self, event: IncidentEvent) -> None:
        now = datetime.now(UTC)

        async with self._session_maker() as session:
            dedup_result = await dedup.dedup_or_register(
                session, event, window_minutes=self._settings.dedup_window_minutes, now=now,
            )
            if dedup_result.kind == "DUPLICATE":
                await self._slack.post(
                    f"🔁 기존 인시던트 재발 (총 {dedup_result.occurrence_count}회) — "
                    f"{event.service} @ {event.commit_sha[:8]} {event.error_class}"
                )
                return

            allowed = await cost_guard.check_daily_cap(
                session, cap_usd=self._settings.daily_cost_cap_usd, now=now,
            )
            if not allowed:
                await self._slack.post(
                    f"💸 일일 LLM 비용 cap (${self._settings.daily_cost_cap_usd}) 초과 — 분석 거절"
                )
                return

            run = AnalysisRun(incident_id=dedup_result.incident_id, status="ANALYZING", started_at=now)
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = f"run-{run.id}"

            await self._slack.post(
                f"🚨 에러 감지 — {event.service} @ {event.commit_sha[:8]} ({event.error_class})"
            )

            worktree = None
            try:
                logs = await self._log_fetcher.fetch_recent_errors(
                    service=event.service, commit_sha=event.commit_sha,
                    window_minutes=self._settings.log_query_window_minutes,
                )
                worktree = await self._repo_manager.checkout_at_sha(event.commit_sha)
                await self._slack.post(
                    f"🔍 분석 시작 — Claude Agent가 코드 탐색 (로그 {len(logs)}건)"
                )

                start = time.monotonic()
                result = await self._analyzer.analyze(
                    worktree_path=worktree, error_class=event.error_class,
                    commit_sha=event.commit_sha, log_lines=logs,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                await cost_guard.record_usage(
                    session, run_id=run.id, model=result.model,
                    input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd, tool_calls_count=result.tool_calls_count,
                    latency_ms=latency_ms,
                )

                # 카테고리별 분기
                issue_url, pr_url = await self._route_by_category(
                    session=session, event=event, result=result,
                    incident_id=dedup_result.incident_id, run_id=run_id, now=now,
                )

                run.status = "COMPLETED"
                run.category = result.category
                run.confidence = result.confidence
                run.root_cause = result.root_cause
                run.completed_at = datetime.now(UTC)
                await session.commit()

                short = result.root_cause[:120]
                await self._slack.post(build_slack_message(
                    category=result.category, issue_url=issue_url, pr_url=pr_url,
                    confidence=result.confidence, cost_usd=result.cost_usd,
                    latency_ms=latency_ms, short_root_cause=short,
                ))
            except RepoManagerError as exc:
                run.status = "FAILED"
                run.error_message = str(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"❌ 코드 체크아웃 실패: {event.commit_sha[:8]} ({exc})")
            except Exception as exc:  # noqa: BLE001 — orchestrator safety
                logger.exception("orchestrator error")
                run.status = "FAILED"
                run.error_message = repr(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"⚠️ 분석 실패: {exc}")
            finally:
                if worktree is not None:
                    await self._repo_manager.cleanup_worktree(worktree)

    async def _route_by_category(
        self,
        *,
        session,
        event: IncidentEvent,
        result: AnalysisResult,
        incident_id: int,
        run_id: str,
        now: datetime,
    ) -> tuple[str, str | None]:
        """카테고리별로 Issue/PR 생성. (issue_url, pr_url_or_None) 반환."""
        category = result.category
        labels_base = ["ai-incident"]

        if category == "CODE_BUG" and result.confidence >= 0.7 and result.patch is not None:
            issue_body = build_code_bug_issue_body(
                result=result, service=event.service,
                commit_sha=event.commit_sha, run_id=run_id,
            )
            issue = await self._github.create_issue(
                title=f"[AI] {event.error_class} in {event.service}",
                body=issue_body,
                labels=labels_base + ["needs-human-review"],
            )
            pr = await self._github.create_pull_request_with_patch(
                issue_number=issue.number,
                branch=f"ai-fix/issue-{issue.number}",
                title=f"[AI Fix] #{issue.number} - {result.root_cause[:60]}",
                body=build_code_bug_pr_body(result=result, issue_number=issue.number, run_id=run_id),
                labels=labels_base + ["human-review-required"],
                patch=result.patch,
                commit_message=f"fix: {result.root_cause[:60]} (Fixes #{issue.number})",
            )
            from ai_bot.db.models import Incident
            await session.execute(
                Incident.__table__.update()
                .where(Incident.id == incident_id)
                .values(github_issue_number=issue.number)
            )
            return issue.url, pr.url

        if category == "BENIGN_ERROR" and result.confidence >= 0.7 and result.patch is not None:
            # 24h 차단 확인
            in_cool = await benign_cooldown.is_benign_in_cooldown(
                session, incident_id=incident_id, hours=24, now=now,
            )
            if in_cool:
                # 재발화: 댓글만, 새 PR 안 만듦. Plan 3 단순화 — Issue만 새로 만들고 PR 안 만듦
                issue = await self._github.create_issue(
                    title=f"[AI] (BENIGN repeat) {event.error_class}",
                    body=f"동일 fingerprint가 24h 내 BENIGN으로 분류됨 (run: {run_id}). 새 PR 생성 안 함.",
                    labels=labels_base + ["noise-reduction", "duplicate"],
                )
                return issue.url, None

            issue_body = (
                f"## 🔇 노이즈 에러\n\n"
                f"**서비스**: {event.service} @ `{event.commit_sha[:8]}`\n\n"
                f"### 추정 원인\n{result.root_cause}\n\n"
                f"자동 PR 생성 + alert rule 조정 제안 Issue 별도 생성됨."
            )
            issue = await self._github.create_issue(
                title=f"[AI] BENIGN {event.error_class}",
                body=issue_body,
                labels=labels_base + ["noise-reduction"],
            )
            pr = await self._github.create_pull_request_with_patch(
                issue_number=issue.number,
                branch=f"ai-fix/issue-{issue.number}",
                title=f"[AI Fix] #{issue.number} - noise reduction: {event.error_class}",
                body=build_benign_pr_body(result=result, issue_number=issue.number, run_id=run_id),
                labels=labels_base + ["noise-reduction", "human-review-required"],
                patch=result.patch,
                commit_message=f"chore: handle {event.error_class} as noise (Fixes #{issue.number})",
            )
            # alert rule 조정 제안 Issue 별도 생성
            await self._github.create_issue(
                title=f"[AI Proposal] alert rule 조정 — {event.error_class}",
                body=build_benign_alert_proposal_body(
                    result=result, related_pr_number=pr.number, run_id=run_id,
                ),
                labels=labels_base + ["noise-reduction", "alert-rule-proposal"],
            )
            return issue.url, pr.url

        if category == "DATA_ANOMALY":
            body = build_data_anomaly_issue_body(
                result=result, service=event.service,
                commit_sha=event.commit_sha, run_id=run_id,
            )
            issue = await self._github.create_issue(
                title=f"[AI] DATA_ANOMALY: {event.error_class} in {event.service}",
                body=body, labels=labels_base + ["data-anomaly", "needs-human-review"],
            )
            return issue.url, None

        if category == "INFRA_ISSUE":
            body = build_infra_issue_body(
                result=result, service=event.service,
                commit_sha=event.commit_sha, run_id=run_id,
            )
            issue = await self._github.create_issue(
                title=f"[AI] INFRA_ISSUE: {event.error_class} in {event.service}",
                body=body, labels=labels_base + ["infra-issue", "needs-human-review"],
            )
            return issue.url, None

        # INSUFFICIENT_CONTEXT 또는 confidence < 0.7
        body = build_insufficient_context_issue_body(
            result=result, service=event.service,
            commit_sha=event.commit_sha, run_id=run_id,
        )
        issue = await self._github.create_issue(
            title=f"[AI] needs review: {event.error_class}",
            body=body, labels=labels_base + ["insufficient-context", "needs-human-review"],
        )
        return issue.url, None
