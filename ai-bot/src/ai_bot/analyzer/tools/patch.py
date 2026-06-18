from __future__ import annotations

from ai_bot.analyzer.result import Patch
from ai_bot.analyzer.tools import ToolContext, ToolError, normalize_and_validate_path

MAX_PATCH_LINES = 30


def propose_patch(
    ctx: ToolContext, *, file_path: str, old_content: str, new_content: str,
) -> str:
    """Register a single-file patch (replace old_content with new_content).

    Restrictions: file must be in allowlist, new_content must be <= 30 lines.
    Calling again on the same file_path replaces the previous patch.
    """
    normalize_and_validate_path(ctx.worktree_path, file_path)  # allowlist + worktree 검증

    new_line_count = len(new_content.splitlines())
    if new_line_count > MAX_PATCH_LINES:
        raise ToolError(f"patch exceeds {MAX_PATCH_LINES} line limit (got {new_line_count})")

    # 기존 동일 파일 patch 제거
    ctx.patches = [p for p in ctx.patches if p.file_path != file_path]
    ctx.patches.append(Patch(file_path=file_path, old_content=old_content, new_content=new_content))
    return f"patch registered for {file_path} ({new_line_count} lines)"
