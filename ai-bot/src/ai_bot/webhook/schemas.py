from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GrafanaAlert(BaseModel):
    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None


class GrafanaWebhookPayload(BaseModel):
    receiver: str = ""
    status: Literal["firing", "resolved"] = "firing"
    alerts: list[GrafanaAlert] = Field(default_factory=list)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    groupLabels: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    version: str = ""


class IncidentEvent(BaseModel):
    """봇 내부에서 쓰는 정규화된 incident 표현."""

    service: str
    commit_sha: str
    error_class: str = "Unknown"
    request_id: str | None = None
    grafana_alert_url: str | None = None

    @classmethod
    def from_grafana(cls, payload: GrafanaWebhookPayload) -> IncidentEvent:
        labels = payload.commonLabels or {}
        # commonLabels에 없으면 첫 alert의 labels로 fallback
        if not labels and payload.alerts:
            labels = payload.alerts[0].labels

        return cls(
            service=labels.get("service", "unknown"),
            commit_sha=labels.get("commit_sha", "unknown"),
            error_class=labels.get("error_class", "Unknown"),
            request_id=labels.get("request_id"),
            grafana_alert_url=payload.externalURL or None,
        )
