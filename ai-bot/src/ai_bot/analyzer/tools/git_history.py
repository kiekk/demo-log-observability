from __future__ import annotations

import subprocess

from ai_bot.analyzer.tools import ToolContext, ToolError, normalize_and_validate_path

MAX_OUTPUT_BYTES = 50 * 1024


def _run_git(cwd, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise ToolError("git command timed out") from None
    if proc.returncode != 0:
        raise ToolError(f"git failed: {proc.stderr.strip()[:500]}")
    out = proc.stdout
    if len(out.encode()) > MAX_OUTPUT_BYTES:
        return out[:MAX_OUTPUT_BYTES] + "\n[...truncated]"
    return out


def git_log(ctx: ToolContext, *, relative_path: str | None, limit: int = 10) -> str:
    """Show recent commits affecting an optional path. Date + author + subject."""
    args = ["log", f"-n{max(1, min(limit, 50))}", "--pretty=format:%h %ad %an %s", "--date=short"]
    if relative_path:
        normalize_and_validate_path(ctx.worktree_path, relative_path)  # 검증만
        args.extend(["--", relative_path])
    return _run_git(ctx.worktree_path, args) or "(no commits)"


def git_diff(
    ctx: ToolContext, *, base: str, head: str, relative_path: str | None = None,
) -> str:
    """Show diff between two revisions, optionally limited to a path."""
    args = ["diff", f"{base}..{head}"]
    if relative_path:
        normalize_and_validate_path(ctx.worktree_path, relative_path)
        args.extend(["--", relative_path])
    return _run_git(ctx.worktree_path, args) or "(no changes)"
