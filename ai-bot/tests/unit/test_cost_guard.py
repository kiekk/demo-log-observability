from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, Incident, LlmUsage
from ai_bot.safety.cost_guard import check_daily_cap, record_usage


@pytest.mark.asyncio
async def test_check_daily_cap_under_limit_passes(db_session: AsyncSession) -> None:
    allowed = await check_daily_cap(db_session, cap_usd=5.0, now=datetime.now(UTC))
    assert allowed is True


@pytest.mark.asyncio
async def test_check_daily_cap_over_limit_blocks(db_session: AsyncSession) -> None:
    t0 = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    incident = Incident(fingerprint="fp", service="s", commit_sha="c", error_class="E", request_id="r", occurrence_count=1)
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=t0)
    db_session.add(run)
    await db_session.flush()
    db_session.add(LlmUsage(run_id=run.id, model="x", input_tokens=0, output_tokens=0, cost_usd=6.0, tool_calls_count=0, latency_ms=0))
    await db_session.commit()

    allowed = await check_daily_cap(db_session, cap_usd=5.0, now=t0 + timedelta(hours=1))
    assert allowed is False


@pytest.mark.asyncio
async def test_check_daily_cap_yesterday_usage_does_not_count(db_session: AsyncSession) -> None:
    today = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    yesterday = today - timedelta(days=1)

    incident = Incident(fingerprint="fp", service="s", commit_sha="c", error_class="E", request_id="r", occurrence_count=1)
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=yesterday)
    db_session.add(run)
    await db_session.flush()
    db_session.add(LlmUsage(run_id=run.id, model="x", input_tokens=0, output_tokens=0, cost_usd=100.0, tool_calls_count=0, latency_ms=0))
    await db_session.commit()

    allowed = await check_daily_cap(db_session, cap_usd=5.0, now=today)
    assert allowed is True


@pytest.mark.asyncio
async def test_record_usage_persists(db_session: AsyncSession) -> None:
    incident = Incident(fingerprint="fp", service="s", commit_sha="c", error_class="E", request_id="r", occurrence_count=1)
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=datetime.now(UTC))
    db_session.add(run)
    await db_session.flush()

    await record_usage(
        db_session, run_id=run.id, model="claude-sonnet-4-6",
        input_tokens=1000, output_tokens=500, cost_usd=0.05, tool_calls_count=3, latency_ms=12000,
    )
    from sqlalchemy import select
    res = await db_session.execute(select(LlmUsage).where(LlmUsage.run_id == run.id))
    fetched = res.scalar_one()
    assert fetched.cost_usd == 0.05
