from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from ai_bot.analyzer.prompts import SYSTEM_PROMPT, build_user_prompt
from ai_bot.analyzer.result import AnalysisResult
from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.db_schema import read_db_schema as _read_db_schema
from ai_bot.analyzer.tools.filesystem import grep as _grep
from ai_bot.analyzer.tools.filesystem import read_file as _read_file
from ai_bot.analyzer.tools.finding import report_finding as _report_finding
from ai_bot.analyzer.tools.git_history import git_diff as _git_diff
from ai_bot.analyzer.tools.git_history import git_log as _git_log
from ai_bot.analyzer.tools.patch import propose_patch as _propose_patch

logger = logging.getLogger(__name__)


class ClaudeAnalyzerError(Exception):
    pass


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def _build_mcp_server(ctx: ToolContext):
    """Build an in-process MCP server with all 7 tools bound to the given ctx."""

    @tool(
        "read_file",
        "Read a source file. Allowed dirs: src/main/, src/test/, src/main/resources/db/migration/",
        {"relative_path": str},
    )
    async def t_read_file(args: dict) -> dict:
        try:
            content = _read_file(ctx, relative_path=args["relative_path"])
            return _ok(content)
        except ToolError as exc:
            return _err(str(exc))

    @tool(
        "grep",
        "Regex search files under a path_prefix. Returns up to 50 matching lines with file:line context.",
        {"pattern": str, "path_prefix": str},
    )
    async def t_grep(args: dict) -> dict:
        try:
            result = _grep(
                ctx,
                pattern=args["pattern"],
                path_prefix=args.get("path_prefix", "src/main"),
            )
            return _ok(result)
        except ToolError as exc:
            return _err(str(exc))

    @tool(
        "git_log",
        "Show recent commits (up to 50). Pass relative_path to limit to a file.",
        {"relative_path": str, "limit": int},
    )
    async def t_git_log(args: dict) -> dict:
        try:
            result = _git_log(
                ctx,
                relative_path=args.get("relative_path") or None,
                limit=int(args.get("limit", 10)),
            )
            return _ok(result)
        except ToolError as exc:
            return _err(str(exc))

    @tool(
        "git_diff",
        "Show diff between base..head revisions. Optionally limit to relative_path.",
        {"base": str, "head": str, "relative_path": str},
    )
    async def t_git_diff(args: dict) -> dict:
        try:
            result = _git_diff(
                ctx,
                base=args["base"],
                head=args["head"],
                relative_path=args.get("relative_path") or None,
            )
            return _ok(result)
        except ToolError as exc:
            return _err(str(exc))

    @tool(
        "read_db_schema",
        "Read Flyway migration files. Pass table to filter by table name keyword.",
        {"table": str},
    )
    async def t_read_db_schema(args: dict) -> dict:
        try:
            result = _read_db_schema(ctx, table=args.get("table") or None)
            return _ok(result)
        except ToolError as exc:
            return _err(str(exc))

    @tool(
        "propose_patch",
        (
            "Register a single-file patch (replace old_content with new_content, ≤30 lines). "
            "Required before report_finding for CODE_BUG or BENIGN_ERROR."
        ),
        {"file_path": str, "old_content": str, "new_content": str},
    )
    async def t_propose_patch(args: dict) -> dict:
        try:
            result = _propose_patch(
                ctx,
                file_path=args["file_path"],
                old_content=args["old_content"],
                new_content=args["new_content"],
            )
            return _ok(result)
        except ToolError as exc:
            return _err(str(exc))

    @tool(
        "report_finding",
        (
            "Final reporting — call EXACTLY ONCE at the end. "
            "Fields: category (CODE_BUG|DATA_ANOMALY|INFRA_ISSUE|INSUFFICIENT_CONTEXT|BENIGN_ERROR), "
            "confidence (0.0–1.0), root_cause, and optional: data_hypothesis, "
            "verification_sql, verification_logql, infra_checklist, related_metrics, alert_rule_proposal."
        ),
        {
            "category": str,
            "confidence": float,
            "root_cause": str,
            "data_hypothesis": str,
            "verification_sql": list,
            "verification_logql": list,
            "infra_checklist": list,
            "related_metrics": list,
            "alert_rule_proposal": str,
        },
    )
    async def t_report_finding(args: dict) -> dict:
        try:
            result = _report_finding(
                ctx,
                category=args["category"],
                confidence=float(args["confidence"]),
                root_cause=args["root_cause"],
                data_hypothesis=args.get("data_hypothesis") or None,
                verification_sql=args.get("verification_sql") or None,
                verification_logql=args.get("verification_logql") or None,
                infra_checklist=args.get("infra_checklist") or None,
                related_metrics=args.get("related_metrics") or None,
                alert_rule_proposal=args.get("alert_rule_proposal") or None,
            )
            return _ok(result)
        except ToolError as exc:
            return _err(str(exc))

    return create_sdk_mcp_server(
        name="incident-bot-tools",
        version="1.0.0",
        tools=[
            t_read_file,
            t_grep,
            t_git_log,
            t_git_diff,
            t_read_db_schema,
            t_propose_patch,
            t_report_finding,
        ],
    )


class ClaudeAnalyzer:
    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-5",
        max_turns: int = 20,
        timeout_seconds: float = 300.0,
    ) -> None:
        self._model = model
        self._max_turns = max_turns
        self._timeout = timeout_seconds

    async def analyze(
        self,
        *,
        worktree_path: Path,
        error_class: str,
        commit_sha: str,
        log_lines: list,
    ) -> AnalysisResult:
        ctx = ToolContext(worktree_path=worktree_path)
        mcp_server = _build_mcp_server(ctx)

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            model=self._model,
            max_turns=self._max_turns,
            mcp_servers={"incident-bot-tools": mcp_server},
            allowed_tools=[
                "read_file",
                "grep",
                "git_log",
                "git_diff",
                "read_db_schema",
                "propose_patch",
                "report_finding",
            ],
            permission_mode="bypassPermissions",
        )

        user_prompt = build_user_prompt(
            error_class=error_class,
            commit_sha=commit_sha,
            log_lines=log_lines,
            worktree_path=worktree_path,
        )

        start = time.monotonic()
        input_tokens = 0
        output_tokens = 0
        tool_calls = 0
        cost_usd = 0.0

        try:
            async with asyncio.timeout(self._timeout):
                async for message in query(prompt=user_prompt, options=options):
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                tool_calls += 1
                        if message.usage:
                            input_tokens += message.usage.get("input_tokens", 0)
                            output_tokens += message.usage.get("output_tokens", 0)
                    elif isinstance(message, ResultMessage):
                        if message.total_cost_usd is not None:
                            cost_usd = message.total_cost_usd
                        if message.usage:
                            input_tokens = message.usage.get("input_tokens", input_tokens)
                            output_tokens = message.usage.get("output_tokens", output_tokens)
                        if message.is_error:
                            error_detail = message.result or str(message.errors)
                            raise ClaudeAnalyzerError(
                                f"Claude SDK returned error: {error_detail}"
                            )
        except asyncio.TimeoutError:
            raise ClaudeAnalyzerError(
                f"analysis timed out after {self._timeout}s"
            ) from None

        latency_ms = int((time.monotonic() - start) * 1000)

        if not ctx.findings:
            raise ClaudeAnalyzerError(
                "Claude did not call report_finding. "
                "Increase max_turns or check prompt."
            )

        result = ctx.findings[-1]
        return result.model_copy(
            update={
                "model": self._model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
                "tool_calls_count": tool_calls,
                "latency_ms": latency_ms,
            }
        )
