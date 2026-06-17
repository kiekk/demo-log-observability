from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from ai_bot.config import Settings
from ai_bot.webhook.schemas import GrafanaWebhookPayload, IncidentEvent

IncidentHandler = Callable[[IncidentEvent], Awaitable[None]]


def build_router(
    *,
    settings: Settings,
    on_incident: IncidentHandler,
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/grafana")
    async def receive_grafana_webhook(
        payload: GrafanaWebhookPayload,
        background: BackgroundTasks,
        authorization: str | None = Header(default=None),
    ):
        _verify_token(authorization, settings.webhook_token)

        if payload.status == "resolved":
            return _no_content()

        event = IncidentEvent.from_grafana(payload)
        background.add_task(on_incident, event)
        return _accepted({"service": event.service, "commit_sha": event.commit_sha})

    return router


def _verify_token(authorization: str | None, expected: str) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _accepted(body: dict) -> "object":
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body)


def _no_content() -> "object":
    from fastapi.responses import Response

    return Response(status_code=status.HTTP_204_NO_CONTENT)
