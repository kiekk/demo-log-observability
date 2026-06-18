from __future__ import annotations

import re

from ai_bot.analyzer.tools import ToolContext, ToolError, normalize_and_validate_path

MAX_FILE_BYTES = 200 * 1024  # 200KB per read
MAX_GREP_MATCHES = 50


def read_file(ctx: ToolContext, *, relative_path: str) -> str:
    """Read a file from the worktree. Returns content (truncated to 200KB)."""
    abs_path = normalize_and_validate_path(ctx.worktree_path, relative_path)
    if not abs_path.exists():
        raise ToolError(f"file not found: {relative_path}")
    if not abs_path.is_file():
        raise ToolError(f"not a file: {relative_path}")
    data = abs_path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        return data[:MAX_FILE_BYTES].decode(errors="replace") + f"\n\n[...truncated, {len(data)} bytes total]"
    return data.decode(errors="replace")


def grep(ctx: ToolContext, *, pattern: str, path_prefix: str = "src/main") -> str:
    """Search files in the worktree for a regex pattern. Returns matches with file:line context."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"invalid regex: {exc}") from exc

    # Allowlist root 확인 — 디렉토리 path_prefix는 trailing slash 없이 올 수 있으므로 보정
    prefix_with_slash = path_prefix.rstrip("/") + "/"
    root = normalize_and_validate_path(ctx.worktree_path, prefix_with_slash)
    if not root.exists():
        raise ToolError(f"path_prefix not found: {path_prefix}")

    matches: list[str] = []
    for file in root.rglob("*"):
        if not file.is_file():
            continue
        try:
            text = file.read_text(errors="replace")
        except OSError:
            continue
        rel = file.relative_to(ctx.worktree_path)
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{rel}:{i}: {line.strip()}")
                if len(matches) >= MAX_GREP_MATCHES:
                    matches.append(f"[...stopped at {MAX_GREP_MATCHES} matches]")
                    return "\n".join(matches)
    if not matches:
        return f"no matches for {pattern!r} in {path_prefix}"
    return "\n".join(matches)
