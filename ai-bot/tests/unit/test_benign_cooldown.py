from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, Incident
from ai_bot.safety.benign_cooldown import is_benign_in_cooldown


def _make_incident(fp: str = "fp-1") -> Incident:
    return Incident(
        fingerprint=fp, service="x", commit_sha="c", error_class="E", request_id="r", occurrence_count=1,
    )


@pytest.mark.asyncio
async def test_no_prior_benign_returns_false(db_session: AsyncSession) -> None:
    inc = _make_incident()
    db_session.add(inc)
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=datetime.now(UTC))
    assert in_cool is False


@pytest.mark.asyncio
async def test_recent_benign_returns_true(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    inc = _make_incident()
    db_session.add(inc)
    await db_session.flush()
    db_session.add(AnalysisRun(
        incident_id=inc.id, status="COMPLETED", category="BENIGN_ERROR",
        started_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=2),
    ))
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=now)
    assert in_cool is True


@pytest.mark.asyncio
async def test_old_benign_outside_window_returns_false(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    inc = _make_incident()
    db_session.add(inc)
    await db_session.flush()
    db_session.add(AnalysisRun(
        incident_id=inc.id, status="COMPLETED", category="BENIGN_ERROR",
        started_at=now - timedelta(days=2),
        completed_at=now - timedelta(days=2),
    ))
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=now)
    assert in_cool is False


@pytest.mark.asyncio
async def test_recent_codebug_does_not_count(db_session: AsyncSession) -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    inc = _make_incident()
    db_session.add(inc)
    await db_session.flush()
    db_session.add(AnalysisRun(
        incident_id=inc.id, status="COMPLETED", category="CODE_BUG",
        started_at=now - timedelta(hours=1), completed_at=now - timedelta(hours=1),
    ))
    await db_session.commit()
    in_cool = await is_benign_in_cooldown(db_session, incident_id=inc.id, hours=24, now=now)
    assert in_cool is False
