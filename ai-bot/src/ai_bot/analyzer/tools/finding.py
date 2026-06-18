from __future__ import annotations

from typing import Literal

from ai_bot.analyzer.result import AnalysisResult
from ai_bot.analyzer.tools import ToolContext, ToolError


def report_finding(
    ctx: ToolContext,
    *,
    category: Literal["CODE_BUG", "DATA_ANOMALY", "INFRA_ISSUE", "INSUFFICIENT_CONTEXT", "BENIGN_ERROR"],
    confidence: float,
    root_cause: str,
    data_hypothesis: str | None = None,
    verification_sql: list[str] | None = None,
    verification_logql: list[str] | None = None,
    infra_checklist: list[str] | None = None,
    related_metrics: list[str] | None = None,
    alert_rule_proposal: str | None = None,
) -> str:
    """Final reporting tool. Must be called exactly once at the end of analysis.

    Field requirements by category:
      - CODE_BUG: propose_patch must have been called (at least one patch in context)
      - DATA_ANOMALY: data_hypothesis required; verification_sql/logql encouraged
      - INFRA_ISSUE: infra_checklist required
      - BENIGN_ERROR: propose_patch + alert_rule_proposal encouraged
      - INSUFFICIENT_CONTEXT: just root_cause
    """
    if not 0.0 <= confidence <= 1.0:
        raise ToolError("confidence must be in [0.0, 1.0]")

    patch = ctx.patches[-1] if ctx.patches else None

    if category == "CODE_BUG" and patch is None:
        raise ToolError("CODE_BUG: patch is required (call propose_patch first)")
    if category == "DATA_ANOMALY" and not data_hypothesis:
        raise ToolError("DATA_ANOMALY: data_hypothesis is required")
    if category == "INFRA_ISSUE" and not infra_checklist:
        raise ToolError("INFRA_ISSUE: infra_checklist is required")

    result = AnalysisResult(
        category=category,
        confidence=confidence,
        root_cause=root_cause,
        patch=patch if category in ("CODE_BUG", "BENIGN_ERROR") else None,
        data_hypothesis=data_hypothesis,
        verification_sql=verification_sql or [],
        verification_logql=verification_logql or [],
        infra_checklist=infra_checklist or [],
        related_metrics=related_metrics or [],
        alert_rule_proposal=alert_rule_proposal,
    )
    ctx.findings.clear()
    ctx.findings.append(result)
    return f"finding recorded: category={category}, confidence={confidence:.2f}"
