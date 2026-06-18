from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_bot.analyzer.fake import FakeAnalyzer
from ai_bot.analyzer.result import AnalysisResult
from ai_bot.config import Settings
from ai_bot.db.models import Base, Incident
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.github_client import GitHubClient
from ai_bot.services.log_fetcher import LogFetcher
from ai_bot.services.repo_manager import RepoManager
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.schemas import IncidentEvent


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/owner/repo.git")
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


@pytest.mark.asyncio
async def test_handle_first_incident_completes(settings, session_maker, tmp_path: Path) -> None:
    fake_logs: list = []
    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = fake_logs

    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.return_value = tmp_path / "wt"
    repo_manager.cleanup_worktree.return_value = None

    slack = SlackNotifier(webhook_url="x", dry_run=True)
    analyzer = FakeAnalyzer()

    orch = Orchestrator(
        settings=settings,
        session_maker=session_maker,
        log_fetcher=log_fetcher,
        repo_manager=repo_manager,
        slack=slack,
        analyzer=analyzer,
        github=AsyncMock(spec=GitHubClient),
    )
    event = IncidentEvent(service="demo-buggy-service", commit_sha="abc123", error_class="NPE")
    await orch.handle(event)

    repo_manager.checkout_at_sha.assert_awaited_once()
    repo_manager.cleanup_worktree.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_event_skips_analysis(settings, session_maker, tmp_path: Path) -> None:
    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = []
    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.return_value = tmp_path / "wt"

    slack = SlackNotifier(webhook_url="x", dry_run=True)
    orch = Orchestrator(
        settings=settings, session_maker=session_maker,
        log_fetcher=log_fetcher, repo_manager=repo_manager,
        slack=slack, analyzer=FakeAnalyzer(),
        github=AsyncMock(spec=GitHubClient),
    )
    event = IncidentEvent(service="demo-buggy-service", commit_sha="abc", error_class="NPE")

    await orch.handle(event)
    await orch.handle(event)  # 즉시 두 번째 호출 → DUPLICATE

    assert repo_manager.checkout_at_sha.await_count == 1


@pytest.mark.asyncio
async def test_repo_failure_marks_run_failed(settings, session_maker, tmp_path: Path) -> None:
    from ai_bot.services.repo_manager import RepoManagerError

    log_fetcher = AsyncMock(spec=LogFetcher)
    log_fetcher.fetch_recent_errors.return_value = []
    repo_manager = AsyncMock(spec=RepoManager)
    repo_manager.checkout_at_sha.side_effect = RepoManagerError("clone failed")

    slack = SlackNotifier(webhook_url="x", dry_run=True)
    orch = Orchestrator(
        settings=settings, session_maker=session_maker,
        log_fetcher=log_fetcher, repo_manager=repo_manager,
        slack=slack, analyzer=FakeAnalyzer(),
        github=AsyncMock(spec=GitHubClient),
    )
    event = IncidentEvent(service="demo-buggy-service", commit_sha="abc", error_class="NPE")
    await orch.handle(event)
    repo_manager.cleanup_worktree.assert_not_awaited()
