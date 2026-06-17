from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import Incident
from ai_bot.webhook.schemas import IncidentEvent


@dataclass
class DedupResult:
    kind: Literal["NEW", "DUPLICATE", "EXPIRED"]
    incident_id: int
    occurrence_count: int


def compute_fingerprint(event: IncidentEvent) -> str:
    raw = f"{event.service}|{event.commit_sha}|{event.error_class}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def dedup_or_register(
    session: AsyncSession,
    event: IncidentEvent,
    *,
    window_minutes: int,
    now: datetime,
) -> DedupResult:
    fp = compute_fingerprint(event)
    result = await session.execute(select(Incident).where(Incident.fingerprint == fp))
    existing = result.scalar_one_or_none()

    if existing is None:
        incident = Incident(
            fingerprint=fp,
            service=event.service,
            commit_sha=event.commit_sha,
            error_class=event.error_class,
            request_id=event.request_id,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)
        return DedupResult(kind="NEW", incident_id=incident.id, occurrence_count=1)

    existing_last = existing.last_seen
    if existing_last.tzinfo is None:
        from datetime import UTC
        existing_last = existing_last.replace(tzinfo=UTC)
    within_window = (now - existing_last) <= timedelta(minutes=window_minutes)

    existing.occurrence_count += 1
    existing.last_seen = now
    await session.commit()
    await session.refresh(existing)

    kind: Literal["DUPLICATE", "EXPIRED"] = "DUPLICATE" if within_window else "EXPIRED"
    return DedupResult(kind=kind, incident_id=existing.id, occurrence_count=existing.occurrence_count)
