import os

import pytest

from ai_bot.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_TOKEN", "test-token-123")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/owner/repo.git")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")

    settings = Settings()  # type: ignore[call-arg]
    assert settings.webhook_token == "test-token-123"
    assert settings.loki_url == "http://loki:3100"
    assert settings.dry_run is False  # default
    assert settings.daily_cost_cap_usd == 5.0  # default
    assert settings.dedup_window_minutes == 10  # default
    assert settings.max_concurrent_analyses == 2  # default


def test_settings_dry_run_truthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("LOKI_URL", "x")
    monkeypatch.setenv("GITHUB_REPO", "x")
    monkeypatch.setenv("GITHUB_REPO_URL", "x")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "x")
    monkeypatch.setenv("DB_PATH", "x")
    monkeypatch.setenv("DRY_RUN", "true")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.dry_run is True
