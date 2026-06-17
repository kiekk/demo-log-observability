from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, Incident, LlmUsage


@pytest.mark.asyncio
async def test_incident_insert_and_query(db_session: AsyncSession) -> None:
    incident = Incident(
        fingerprint="fp-test-1",
        service="demo-buggy-service",
        commit_sha="abc123",
        error_class="NullPointerException",
        request_id="r-1",
        occurrence_count=1,
    )
    db_session.add(incident)
    await db_session.commit()

    result = await db_session.execute(select(Incident).where(Incident.fingerprint == "fp-test-1"))
    fetched = result.scalar_one()
    assert fetched.service == "demo-buggy-service"
    assert fetched.commit_sha == "abc123"


@pytest.mark.asyncio
async def test_analysis_run_with_incident(db_session: AsyncSession) -> None:
    incident = Incident(
        fingerprint="fp-test-2",
        service="demo-buggy-service",
        commit_sha="def456",
        error_class="ArithmeticException",
        request_id="r-2",
        occurrence_count=1,
    )
    db_session.add(incident)
    await db_session.flush()

    run = AnalysisRun(
        incident_id=incident.id,
        status="PENDING",
        started_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()

    result = await db_session.execute(select(AnalysisRun).where(AnalysisRun.incident_id == incident.id))
    fetched = result.scalar_one()
    assert fetched.status == "PENDING"


@pytest.mark.asyncio
async def test_llm_usage(db_session: AsyncSession) -> None:
    incident = Incident(
        fingerprint="fp-test-3",
        service="demo-buggy-service",
        commit_sha="ghi789",
        error_class="X",
        request_id="r-3",
        occurrence_count=1,
    )
    db_session.add(incident)
    await db_session.flush()
    run = AnalysisRun(incident_id=incident.id, status="COMPLETED", started_at=datetime.now(UTC))
    db_session.add(run)
    await db_session.flush()
    usage = LlmUsage(
        run_id=run.id,
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.01,
        tool_calls_count=5,
        latency_ms=12345,
    )
    db_session.add(usage)
    await db_session.commit()

    result = await db_session.execute(select(LlmUsage).where(LlmUsage.run_id == run.id))
    fetched = result.scalar_one()
    assert fetched.cost_usd == 0.01
