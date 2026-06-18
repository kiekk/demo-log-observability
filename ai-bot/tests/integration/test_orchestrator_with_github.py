from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_bot.analyzer.result import AnalysisResult, Patch
from ai_bot.config import Settings
from ai_bot.db.models import Base
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.github_client import GitHubClient, IssueRef, PullRequestRef
from ai_bot.services.log_fetcher import LogFetcher
from ai_bot.services.repo_manager import RepoManager
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.schemas import IncidentEvent


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "x/y")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DRY_RUN", "true")
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def session_maker(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def _make_orchestrator(settings, session_maker, analyzer_result, *, tmp_path: Path):
    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = []
    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.return_value = tmp_path / "wt"
    repo_manager.cleanup_worktree.return_value = None
    slack = SlackNotifier(webhook_url="x", dry_run=True)

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value=analyzer_result)

    github = AsyncMock(spec=GitHubClient)
    github.create_issue.return_value = IssueRef(number=42, url="https://github.com/x/y/issues/42")
    github.create_pull_request_with_patch.return_value = PullRequestRef(
        number=43, branch="ai-fix/issue-42", url="https://github.com/x/y/pull/43",
    )

    return Orchestrator(
        settings=settings, session_maker=session_maker,
        log_fetcher=log_fetcher, repo_manager=repo_manager,
        slack=slack, analyzer=analyzer, github=github,
    ), github


@pytest.mark.asyncio
async def test_code_bug_creates_issue_and_pr(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="CODE_BUG", confidence=0.85, root_cause="NPE",
        patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b"),
        model="claude", cost_usd=0.1,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="NPE")
    await orch.handle(event)
    github.create_issue.assert_awaited_once()
    github.create_pull_request_with_patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_data_anomaly_creates_issue_only_no_pr(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="DATA_ANOMALY", confidence=0.82, root_cause="city empty",
        data_hypothesis="city='' for users 100..200",
        verification_sql=["SELECT 1"], verification_logql=["{x}"],
        model="claude", cost_usd=0.1,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="NPE")
    await orch.handle(event)
    github.create_issue.assert_awaited_once()
    github.create_pull_request_with_patch.assert_not_awaited()


@pytest.mark.asyncio
async def test_benign_first_time_creates_pr_and_proposal_issue(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="BENIGN_ERROR", confidence=0.88, root_cause="client disconnect",
        patch=Patch(file_path="src/main/h.kt", old_content="", new_content="x"),
        alert_rule_proposal="exception_class!=ClientAbortException",
        model="claude", cost_usd=0.1,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="ClientAbortException")
    await orch.handle(event)
    # 2 issues (main + alert proposal) + 1 PR
    assert github.create_issue.await_count == 2
    github.create_pull_request_with_patch.assert_awaited_once()


@pytest.mark.asyncio
async def test_low_confidence_falls_to_insufficient_branch(settings, session_maker, tmp_path: Path) -> None:
    result = AnalysisResult(
        category="CODE_BUG", confidence=0.5, root_cause="not sure",
        patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b"),
        model="claude", cost_usd=0.05,
    )
    orch, github = _make_orchestrator(settings, session_maker, result, tmp_path=tmp_path)
    event = IncidentEvent(service="x", commit_sha="abc", error_class="x")
    await orch.handle(event)
    # confidence < 0.7라 PR 없음 (Issue만)
    github.create_issue.assert_awaited_once()
    github.create_pull_request_with_patch.assert_not_awaited()
