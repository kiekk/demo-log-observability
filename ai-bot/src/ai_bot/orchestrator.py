from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from ai_bot.analyzer.result import AnalysisResult
from ai_bot.config import Settings
from ai_bot.db.models import AnalysisRun, Incident
from ai_bot.safety import cost_guard, dedup
from ai_bot.services.log_fetcher import LogFetcher, LogLine
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
    ) -> None:
        self._settings = settings
        self._session_maker = session_maker
        self._log_fetcher = log_fetcher
        self._repo_manager = repo_manager
        self._slack = slack
        self._analyzer = analyzer

    async def handle(self, event: IncidentEvent) -> None:
        now = datetime.now(UTC)

        async with self._session_maker() as session:
            # 1. dedup
            dedup_result = await dedup.dedup_or_register(
                session, event, window_minutes=self._settings.dedup_window_minutes, now=now,
            )
            if dedup_result.kind == "DUPLICATE":
                await self._slack.post(
                    f"🔁 기존 인시던트 재발 (총 {dedup_result.occurrence_count}회) — "
                    f"{event.service} @ {event.commit_sha[:8]} {event.error_class}"
                )
                return

            # 2. cost cap
            allowed = await cost_guard.check_daily_cap(
                session, cap_usd=self._settings.daily_cost_cap_usd, now=now,
            )
            if not allowed:
                await self._slack.post(
                    f"💸 일일 LLM 비용 cap (${self._settings.daily_cost_cap_usd}) 초과 — 분석 거절"
                )
                return

            # 3. run 시작
            run = AnalysisRun(incident_id=dedup_result.incident_id, status="ANALYZING", started_at=now)
            session.add(run)
            await session.commit()
            await session.refresh(run)

            await self._slack.post(
                f"🚨 에러 감지 — {event.service} @ {event.commit_sha[:8]} "
                f"({event.error_class})"
            )

            # 4. 로그 + worktree 준비 + 분석
            worktree = None
            try:
                logs = await self._log_fetcher.fetch_recent_errors(
                    service=event.service,
                    commit_sha=event.commit_sha,
                    window_minutes=self._settings.log_query_window_minutes,
                )
                worktree = await self._repo_manager.checkout_at_sha(event.commit_sha)
                await self._slack.post(
                    f"🔍 분석 시작 — Claude Agent가 코드를 탐색 (로그 {len(logs)}건, "
                    f"worktree: {worktree.name})"
                )

                start = time.monotonic()
                result = await self._analyzer.analyze(
                    worktree_path=worktree,
                    error_class=event.error_class,
                    commit_sha=event.commit_sha,
                    log_lines=logs,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                await cost_guard.record_usage(
                    session,
                    run_id=run.id,
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.cost_usd,
                    tool_calls_count=result.tool_calls_count,
                    latency_ms=latency_ms,
                )

                # 5. 결과 기록 (Plan 2: PR/Issue 생성은 아직 안 함)
                run.status = "COMPLETED"
                run.category = result.category
                run.confidence = result.confidence
                run.root_cause = result.root_cause
                run.completed_at = datetime.now(UTC)
                await session.commit()

                await self._slack.post(
                    f"✅ [FAKE] 분석 완료 — category={result.category}, "
                    f"confidence={result.confidence:.2f}, cost=${result.cost_usd:.3f}\n"
                    f"> {result.root_cause}"
                )
            except RepoManagerError as exc:
                run.status = "FAILED"
                run.error_message = str(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"❌ 코드 체크아웃 실패: {event.commit_sha[:8]} ({exc})")
            except Exception as exc:  # noqa: BLE001 — orchestrator-level safety
                logger.exception("orchestrator error")
                run.status = "FAILED"
                run.error_message = repr(exc)
                run.completed_at = datetime.now(UTC)
                await session.commit()
                await self._slack.post(f"⚠️ 분석 실패: {exc}")
            finally:
                if worktree is not None:
                    await self._repo_manager.cleanup_worktree(worktree)
