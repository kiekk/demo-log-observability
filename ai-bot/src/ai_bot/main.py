from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_bot.analyzer.claude import ClaudeAnalyzer
from ai_bot.config import Settings
from ai_bot.db.session import create_engine, create_session_maker
from ai_bot.orchestrator import Orchestrator
from ai_bot.services.github_client import GitHubClient
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
    github = GitHubClient(
        token=s.github_token,
        repo_full_name=s.github_repo,
        dry_run=s.dry_run,
    )
    analyzer = ClaudeAnalyzer()

    orchestrator = Orchestrator(
        settings=s,
        session_maker=session_maker,
        log_fetcher=log_fetcher,
        repo_manager=repo_manager,
        slack=slack,
        analyzer=analyzer,
        github=github,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await repo_manager.ensure_bare_clone()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_bare_clone failed at startup: %s — will retry per request", exc)
        logger.info("ai-bot ready (dry_run=%s, model=%s)", s.dry_run, analyzer._model)
        yield
        await engine.dispose()

    app = FastAPI(title="ai-bot", lifespan=lifespan)

    async def on_incident(event: IncidentEvent) -> None:
        await orchestrator.handle(event)

    app.include_router(build_router(settings=s, on_incident=on_incident))

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "dry_run": s.dry_run, "model": analyzer._model}

    return app


app = create_app()
