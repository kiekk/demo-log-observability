import subprocess
from pathlib import Path

import pytest

from ai_bot.analyzer.tools import ToolContext, ToolError
from ai_bot.analyzer.tools.git_history import git_diff, git_log


@pytest.fixture
def git_worktree(tmp_path: Path) -> Path:
    (tmp_path / "src/main").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)

    (tmp_path / "src/main/A.kt").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)

    (tmp_path / "src/main/A.kt").write_text("v2\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_log_returns_commits(git_worktree: Path) -> None:
    ctx = ToolContext(worktree_path=git_worktree)
    result = git_log(ctx, relative_path="src/main/A.kt", limit=10)
    assert "first" in result
    assert "second" in result


def test_git_log_no_path_returns_all(git_worktree: Path) -> None:
    ctx = ToolContext(worktree_path=git_worktree)
    result = git_log(ctx, relative_path=None, limit=5)
    assert "first" in result
    assert "second" in result


def test_git_log_path_outside_allowlist_raises(git_worktree: Path) -> None:
    ctx = ToolContext(worktree_path=git_worktree)
    (git_worktree / "outside.txt").write_text("x")
    with pytest.raises(ToolError):
        git_log(ctx, relative_path="outside.txt", limit=5)


def test_git_diff_between_revisions(git_worktree: Path) -> None:
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_worktree, text=True).strip()
    prev_sha = subprocess.check_output(["git", "rev-parse", "HEAD~1"], cwd=git_worktree, text=True).strip()

    ctx = ToolContext(worktree_path=git_worktree)
    result = git_diff(ctx, base=prev_sha, head=head_sha, relative_path="src/main/A.kt")
    assert "v1" in result and "v2" in result
