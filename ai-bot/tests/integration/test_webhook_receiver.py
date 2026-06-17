import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_bot.config import Settings
from ai_bot.webhook.receiver import build_router


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    monkeypatch.setenv("WEBHOOK_TOKEN", "secret-token-123")
    monkeypatch.setenv("LOKI_URL", "http://loki:3100")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/owner/repo.git")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/X")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    received: list = []

    async def handler(event) -> None:
        received.append(event)

    app = FastAPI()
    app.include_router(build_router(settings=settings, on_incident=handler))
    app.state.received = received
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _valid_payload() -> dict:
    return {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
                "annotations": {},
                "startsAt": "2026-06-17T12:00:00Z",
            }
        ],
        "commonLabels": {"service": "demo-buggy-service", "commit_sha": "abc123"},
        "groupLabels": {},
    }


def test_missing_authorization_returns_401(client: TestClient) -> None:
    r = client.post("/webhooks/grafana", json=_valid_payload())
    assert r.status_code == 401


def test_wrong_token_returns_401(client: TestClient) -> None:
    r = client.post(
        "/webhooks/grafana",
        json=_valid_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_valid_request_returns_202_and_triggers_handler(client: TestClient, app: FastAPI) -> None:
    r = client.post(
        "/webhooks/grafana",
        json=_valid_payload(),
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert r.status_code == 202
    assert len(app.state.received) == 1
    assert app.state.received[0].service == "demo-buggy-service"


def test_resolved_status_returns_204_without_handler_call(client: TestClient, app: FastAPI) -> None:
    payload = _valid_payload()
    payload["status"] = "resolved"
    r = client.post(
        "/webhooks/grafana",
        json=payload,
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert r.status_code == 204
    assert len(app.state.received) == 0
