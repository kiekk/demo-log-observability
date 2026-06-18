from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.patch import propose_patch


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    src = tmp_path / "src/main/kotlin"
    src.mkdir(parents=True)
    (src / "Foo.kt").write_text("fun bar() {}\n")
    return tmp_path


def test_propose_patch_records_in_context(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = propose_patch(
        ctx, file_path="src/main/kotlin/Foo.kt",
        old_content="fun bar() {}\n",
        new_content="fun bar(): Int = 0\n",
    )
    assert "registered" in result.lower()
    assert len(ctx.patches) == 1
    assert ctx.patches[0].file_path == "src/main/kotlin/Foo.kt"
    assert ctx.patches[0].new_content == "fun bar(): Int = 0\n"


def test_propose_patch_outside_allowlist_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError):
        propose_patch(
            ctx, file_path=".env",
            old_content="x", new_content="y",
        )


def test_propose_patch_over_30_lines_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    long_new = "line\n" * 31
    with pytest.raises(ToolError, match="30 line"):
        propose_patch(
            ctx, file_path="src/main/kotlin/Foo.kt",
            old_content="fun bar() {}\n",
            new_content=long_new,
        )


def test_propose_patch_replaces_previous(worktree: Path) -> None:
    """동일 파일에 두 번째 호출 시 마지막 것만 유지."""
    ctx = ToolContext(worktree_path=worktree)
    propose_patch(
        ctx, file_path="src/main/kotlin/Foo.kt",
        old_content="fun bar() {}\n", new_content="v1\n",
    )
    propose_patch(
        ctx, file_path="src/main/kotlin/Foo.kt",
        old_content="fun bar() {}\n", new_content="v2\n",
    )
    assert len(ctx.patches) == 1
    assert ctx.patches[0].new_content == "v2\n"
