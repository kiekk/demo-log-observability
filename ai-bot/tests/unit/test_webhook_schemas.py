from ai_bot.webhook.schemas import GrafanaWebhookPayload, IncidentEvent


def test_parse_minimal_grafana_payload() -> None:
    raw = {
        "receiver": "ai-bot-webhook",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "AI Bot - Buggy Service Error",
                    "service": "demo-buggy-service",
                    "commit_sha": "abc123",
                },
                "annotations": {},
                "startsAt": "2026-06-17T12:00:00Z",
            }
        ],
        "commonLabels": {
            "service": "demo-buggy-service",
            "commit_sha": "abc123",
        },
        "groupLabels": {"alertname": "AI Bot - Buggy Service Error"},
    }
    payload = GrafanaWebhookPayload.model_validate(raw)
    assert payload.status == "firing"
    assert payload.commonLabels["service"] == "demo-buggy-service"
    assert payload.commonLabels["commit_sha"] == "abc123"
    assert len(payload.alerts) == 1


def test_to_incident_event() -> None:
    raw = {
        "receiver": "ai-bot-webhook",
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
    payload = GrafanaWebhookPayload.model_validate(raw)
    event = IncidentEvent.from_grafana(payload)
    assert event.service == "demo-buggy-service"
    assert event.commit_sha == "abc123"


def test_resolved_status_returns_empty_events() -> None:
    raw = {
        "receiver": "ai-bot-webhook",
        "status": "resolved",
        "alerts": [],
        "commonLabels": {},
        "groupLabels": {},
    }
    payload = GrafanaWebhookPayload.model_validate(raw)
    assert payload.status == "resolved"
