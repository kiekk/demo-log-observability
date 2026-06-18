from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_bot.db.models import AnalysisRun


async def is_benign_in_cooldown(
    session: AsyncSession, *, incident_id: int, hours: int, now: datetime,
) -> bool:
    """같은 incident가 hours 내 BENIGN_ERROR로 분류된 적 있는지 확인."""
    threshold = now - timedelta(hours=hours)
    stmt = (
        select(AnalysisRun.id)
        .where(
            AnalysisRun.incident_id == incident_id,
            AnalysisRun.category == "BENIGN_ERROR",
            AnalysisRun.completed_at >= threshold,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
