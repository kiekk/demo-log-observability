from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun, LlmUsage


async def check_daily_cap(session: AsyncSession, *, cap_usd: float, now: datetime) -> bool:
    """오늘(UTC) 누적 비용이 cap 미만이면 True 반환."""
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    end_of_today = start_of_today + timedelta(days=1)
    stmt = (
        select(func.coalesce(func.sum(LlmUsage.cost_usd), 0.0))
        .join(AnalysisRun, LlmUsage.run_id == AnalysisRun.id)
        .where(
            AnalysisRun.started_at >= start_of_today,
            AnalysisRun.started_at < end_of_today,
        )
    )
    total = (await session.execute(stmt)).scalar_one()
    return float(total) < cap_usd


async def record_usage(
    session: AsyncSession,
    *,
    run_id: int,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    tool_calls_count: int,
    latency_ms: int,
) -> None:
    usage = LlmUsage(
        run_id=run_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        tool_calls_count=tool_calls_count,
        latency_ms=latency_ms,
    )
    session.add(usage)
    await session.commit()
