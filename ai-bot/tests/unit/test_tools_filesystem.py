from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.filesystem import grep, read_file


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    (tmp_path / "src/main/kotlin").mkdir(parents=True)
    (tmp_path / "src/main/kotlin/Foo.kt").write_text("class Foo {\n  fun bar() {}\n}\n")
    (tmp_path / "src/main/kotlin/Bar.kt").write_text("class Bar {\n  fun baz() {}\n}\n")
    (tmp_path / "secrets.txt").write_text("super-secret\n")
    return tmp_path


def test_read_file_returns_content(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = read_file(ctx, relative_path="src/main/kotlin/Foo.kt")
    assert "class Foo" in result


def test_read_file_outside_allowlist_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError, match="not in allowlist"):
        read_file(ctx, relative_path="secrets.txt")


def test_read_file_escape_via_dotdot_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError):
        read_file(ctx, relative_path="src/main/../../etc/passwd")


def test_read_file_nonexistent_raises(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    with pytest.raises(ToolError, match="not found"):
        read_file(ctx, relative_path="src/main/kotlin/Nope.kt")


def test_grep_finds_matches(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = grep(ctx, pattern=r"fun \w+", path_prefix="src/main")
    assert "Foo.kt" in result
    assert "Bar.kt" in result
    assert "bar()" in result or "baz()" in result


def test_grep_with_no_matches_returns_empty(worktree: Path) -> None:
    ctx = ToolContext(worktree_path=worktree)
    result = grep(ctx, pattern="ZZZ_NOMATCH", path_prefix="src/main")
    assert "no matches" in result.lower()
