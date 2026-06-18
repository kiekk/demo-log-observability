from ai_bot.analyzer.result import AnalysisResult, Patch
from ai_bot.services.pr_templates import (
    build_code_bug_issue_body,
    build_code_bug_pr_body,
    build_data_anomaly_issue_body,
    build_infra_issue_body,
    build_benign_pr_body,
    build_benign_alert_proposal_body,
    build_insufficient_context_issue_body,
    build_slack_message,
)


def _result(category, **overrides) -> AnalysisResult:
    base = {
        "category": category,
        "confidence": 0.85,
        "root_cause": "test root cause",
        "model": "claude-sonnet-4-6",
        "cost_usd": 0.5,
        "tool_calls_count": 10,
        "latency_ms": 30000,
    }
    base.update(overrides)
    return AnalysisResult(**base)


def test_code_bug_issue_body_includes_metadata() -> None:
    body = build_code_bug_issue_body(
        result=_result("CODE_BUG", patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b")),
        service="demo-buggy-service",
        commit_sha="abc123def",
        run_id="run-1",
    )
    assert "demo-buggy-service" in body
    assert "abc123de" in body  # short sha
    assert "test root cause" in body
    assert "ai-bot" in body or "AI" in body


def test_code_bug_pr_body_mentions_review_warning_and_issue_link() -> None:
    body = build_code_bug_pr_body(
        result=_result("CODE_BUG", patch=Patch(file_path="src/main/x.kt", old_content="a", new_content="b")),
        issue_number=42,
        run_id="run-1",
    )
    assert "Fixes #42" in body
    assert "Review carefully" in body or "review" in body.lower()


def test_data_anomaly_body_includes_sql_and_logql() -> None:
    body = build_data_anomaly_issue_body(
        result=_result(
            "DATA_ANOMALY",
            data_hypothesis="city='' for user_id 100..200",
            verification_sql=["SELECT count(*) FROM addresses WHERE city=''"],
            verification_logql=["{service=\"x\"} | json"],
        ),
        service="demo-buggy-service",
        commit_sha="abc123",
        run_id="run-1",
    )
    assert "city=''" in body
    assert "```sql" in body
    assert "```logql" in body
    assert "코드 PR을 자동 생성하지 않았습니다" in body or "no PR" in body.lower() or "PR was not" in body


def test_infra_issue_body_includes_checklist() -> None:
    body = build_infra_issue_body(
        result=_result("INFRA_ISSUE", infra_checklist=["check HikariCP", "check RDS connections"], related_metrics=["{service=\"x\"} | rate"]),
        service="demo-buggy-service",
        commit_sha="abc123",
        run_id="run-1",
    )
    assert "check HikariCP" in body
    assert "check RDS connections" in body


def test_benign_pr_body_mentions_noise() -> None:
    body = build_benign_pr_body(
        result=_result("BENIGN_ERROR", patch=Patch(file_path="src/main/H.kt", old_content="", new_content="x")),
        issue_number=99,
        run_id="run-2",
    )
    assert "noise" in body.lower() or "BENIGN" in body
    assert "Fixes #99" in body


def test_benign_alert_proposal_body() -> None:
    body = build_benign_alert_proposal_body(
        result=_result("BENIGN_ERROR", alert_rule_proposal="exception_class!=ClientAbortException", patch=Patch(file_path="x", old_content="", new_content="")),
        related_pr_number=99,
        run_id="run-2",
    )
    assert "exception_class!=ClientAbortException" in body
    assert "PR #99" in body
    assert "자동 수정하지 않습니다" in body or "do not auto" in body.lower() or "not automatically" in body.lower()


def test_insufficient_context_body() -> None:
    body = build_insufficient_context_issue_body(
        result=_result("INSUFFICIENT_CONTEXT", confidence=0.45),
        service="x", commit_sha="abc", run_id="r",
    )
    assert "0.45" in body or "0.4" in body


def test_slack_message_for_code_bug() -> None:
    msg = build_slack_message(
        category="CODE_BUG",
        issue_url="https://github.com/x/y/issues/42",
        pr_url="https://github.com/x/y/pull/43",
        confidence=0.85,
        cost_usd=0.42,
        latency_ms=135000,
        short_root_cause="NPE in Foo",
    )
    assert "✅" in msg
    assert "pull/43" in msg
    assert "0.85" in msg


def test_slack_message_for_data_anomaly() -> None:
    msg = build_slack_message(
        category="DATA_ANOMALY",
        issue_url="https://github.com/x/y/issues/14",
        pr_url=None,
        confidence=0.82,
        cost_usd=0.38,
        latency_ms=120000,
        short_root_cause="addresses.city empty",
    )
    assert "🔎" in msg
    assert "issues/14" in msg
    assert "pull" not in msg.split("issues/14")[1].split("\n")[0]  # PR 링크 없음


def test_slack_message_for_benign_error() -> None:
    msg = build_slack_message(
        category="BENIGN_ERROR",
        issue_url="https://github.com/x/y/issues/15",
        pr_url="https://github.com/x/y/pull/16",
        confidence=0.88,
        cost_usd=0.3,
        latency_ms=90000,
        short_root_cause="ClientAbortException",
    )
    assert "🔇" in msg
