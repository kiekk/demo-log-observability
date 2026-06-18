from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_bot.analyzer.fake import FakeAnalyzer
from ai_bot.config import Settings
from ai_bot.db.session import create_engine, create_session_maker
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.log_fetcher import LogFetcher
from ai_bot.services.repo_manager import RepoManager
from ai_bot.services.slack_notifier import SlackNotifier
from ai_bot.webhook.receiver import build_router
from ai_bot.webhook.schemas import IncidentEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings()  # type: ignore[call-arg]

    engine = create_engine(s.db_path)
    session_maker = create_session_maker(engine)

    log_fetcher = LogFetcher(loki_url=s.loki_url)
    repo_manager = RepoManager(
        clone_url=s.github_repo_url,
        cache_dir=s.repo_cache_dir,
        worktree_dir=s.worktree_dir,
        github_token=s.github_token,
    )
    slack = SlackNotifier(webhook_url=s.slack_webhook_url, dry_run=s.dry_run)
    analyzer = FakeAnalyzer()

    orchestrator = Orchestrator(
        settings=s,
        session_maker=session_maker,
        log_fetcher=log_fetcher,
        repo_manager=repo_manager,
        slack=slack,
        analyzer=analyzer,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # bare clone 준비 (실패해도 봇은 기동)
        try:
            await repo_manager.ensure_bare_clone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_bare_clone failed at startup: %s — will retry per request", exc)
        logger.info("ai-bot ready (dry_run=%s)", s.dry_run)
        yield
        await engine.dispose()

    app = FastAPI(title="ai-bot", lifespan=lifespan)

    async def on_incident(event: IncidentEvent) -> None:
        await orchestrator.handle(event)

    app.include_router(build_router(settings=s, on_incident=on_incident))

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "dry_run": s.dry_run}

    return app


app = create_app()
