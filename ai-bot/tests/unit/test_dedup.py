from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import Incident
from ai_bot.safety.dedup import DedupResult, compute_fingerprint, dedup_or_register
from ai_bot.webhook.schemas import IncidentEvent


def _event(service: str = "demo-buggy-service", sha: str = "abc123", err: str = "NPE") -> IncidentEvent:
    return IncidentEvent(service=service, commit_sha=sha, error_class=err, request_id="r-1")


def test_compute_fingerprint_is_deterministic() -> None:
    e1 = _event()
    e2 = _event()
    assert compute_fingerprint(e1) == compute_fingerprint(e2)


def test_compute_fingerprint_differs_by_field() -> None:
    assert compute_fingerprint(_event(sha="abc")) != compute_fingerprint(_event(sha="def"))
    assert compute_fingerprint(_event(err="NPE")) != compute_fingerprint(_event(err="OOM"))


@pytest.mark.asyncio
async def test_first_occurrence_returns_NEW(db_session: AsyncSession) -> None:
    event = _event()
    result = await dedup_or_register(db_session, event, window_minutes=10, now=datetime.now(UTC))
    assert result.kind == "NEW"
    assert result.incident_id is not None
    assert result.occurrence_count == 1


@pytest.mark.asyncio
async def test_second_occurrence_within_window_returns_DUPLICATE(db_session: AsyncSession) -> None:
    event = _event()
    t0 = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    first = await dedup_or_register(db_session, event, window_minutes=10, now=t0)
    second = await dedup_or_register(db_session, event, window_minutes=10, now=t0 + timedelta(minutes=5))
    assert first.kind == "NEW"
    assert second.kind == "DUPLICATE"
    assert second.incident_id == first.incident_id
    assert second.occurrence_count == 2


@pytest.mark.asyncio
async def test_occurrence_outside_window_returns_EXPIRED(db_session: AsyncSession) -> None:
    event = _event()
    t0 = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    first = await dedup_or_register(db_session, event, window_minutes=10, now=t0)
    second = await dedup_or_register(db_session, event, window_minutes=10, now=t0 + timedelta(minutes=11))
    assert second.kind == "EXPIRED"
    assert second.incident_id == first.incident_id
    assert second.occurrence_count == 2
