from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.finding import report_finding


@pytest.fixture
def ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(worktree_path=tmp_path)


def test_code_bug_with_patch_records_finding(ctx: ToolContext) -> None:
    from ai_bot.analyzer.result import Patch
    ctx.patches.append(Patch(file_path="src/main/x.kt", old_content="a", new_content="b"))
    result = report_finding(
        ctx, category="CODE_BUG", confidence=0.85, root_cause="NPE in X",
    )
    assert "recorded" in result.lower()
    assert len(ctx.findings) == 1
    assert ctx.findings[0].category == "CODE_BUG"
    assert ctx.findings[0].patch is not None


def test_code_bug_without_patch_raises(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="patch is required"):
        report_finding(ctx, category="CODE_BUG", confidence=0.85, root_cause="x")


def test_data_anomaly_requires_hypothesis(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="data_hypothesis"):
        report_finding(ctx, category="DATA_ANOMALY", confidence=0.8, root_cause="x")


def test_data_anomaly_with_full_fields(ctx: ToolContext) -> None:
    result = report_finding(
        ctx, category="DATA_ANOMALY", confidence=0.82, root_cause="city empty",
        data_hypothesis="city='' for user_id 100~200",
        verification_sql=["SELECT count(*) FROM addresses WHERE city=''"],
        verification_logql=["{service=\"x\"} | json | level=\"ERROR\""],
    )
    assert "recorded" in result.lower()
    assert ctx.findings[0].verification_sql == ["SELECT count(*) FROM addresses WHERE city=''"]


def test_infra_issue_requires_checklist(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="infra_checklist"):
        report_finding(ctx, category="INFRA_ISSUE", confidence=0.7, root_cause="pool")


def test_benign_error_with_patch_and_proposal(ctx: ToolContext) -> None:
    from ai_bot.analyzer.result import Patch
    ctx.patches.append(Patch(file_path="src/main/H.kt", old_content="", new_content="x"))
    result = report_finding(
        ctx, category="BENIGN_ERROR", confidence=0.88,
        root_cause="client disconnect",
        alert_rule_proposal="exception_class!=ClientAbortException",
    )
    assert "recorded" in result.lower()
    assert ctx.findings[0].alert_rule_proposal == "exception_class!=ClientAbortException"


def test_insufficient_context_no_patch_no_extras(ctx: ToolContext) -> None:
    result = report_finding(ctx, category="INSUFFICIENT_CONTEXT", confidence=0.45, root_cause="need cross-service logs")
    assert "recorded" in result.lower()
    assert ctx.findings[0].patch is None


def test_calling_twice_replaces(ctx: ToolContext) -> None:
    report_finding(ctx, category="INSUFFICIENT_CONTEXT", confidence=0.4, root_cause="x")
    report_finding(ctx, category="INSUFFICIENT_CONTEXT", confidence=0.5, root_cause="y")
    assert len(ctx.findings) == 1
    assert ctx.findings[0].confidence == 0.5
