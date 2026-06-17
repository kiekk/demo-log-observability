import subprocess
from pathlib import Path

import pytest

from ai_bot.services.repo_manager import RepoManager


@pytest.fixture
def upstream_repo(tmp_path: Path) -> Path:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=upstream, check=True)
    (upstream / "README.md").write_text("v1\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=upstream, check=True)
    subprocess.run(["git", "tag", "v1"], cwd=upstream, check=True)

    (upstream / "README.md").write_text("v2\n")
    subprocess.run(["git", "add", "."], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=upstream, check=True)
    subprocess.run(["git", "tag", "v2"], cwd=upstream, check=True)

    return upstream


@pytest.mark.asyncio
async def test_first_clone_creates_bare(upstream_repo: Path, tmp_path: Path) -> None:
    mgr = RepoManager(
        clone_url=str(upstream_repo),
        cache_dir=str(tmp_path / "cache"),
        worktree_dir=str(tmp_path / "wt"),
    )
    await mgr.ensure_bare_clone()
    bare = tmp_path / "cache" / "demo.git"
    assert bare.exists()
    assert (bare / "HEAD").exists()


@pytest.mark.asyncio
async def test_checkout_at_sha_creates_worktree(upstream_repo: Path, tmp_path: Path) -> None:
    mgr = RepoManager(
        clone_url=str(upstream_repo),
        cache_dir=str(tmp_path / "cache"),
        worktree_dir=str(tmp_path / "wt"),
    )
    v1_sha = subprocess.check_output(["git", "rev-parse", "v1"], cwd=upstream_repo, text=True).strip()
    worktree = await mgr.checkout_at_sha(v1_sha)
    try:
        assert (worktree / "README.md").read_text() == "v1\n"
    finally:
        await mgr.cleanup_worktree(worktree)


@pytest.mark.asyncio
async def test_cleanup_worktree_removes_it(upstream_repo: Path, tmp_path: Path) -> None:
    mgr = RepoManager(
        clone_url=str(upstream_repo),
        cache_dir=str(tmp_path / "cache"),
        worktree_dir=str(tmp_path / "wt"),
    )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream_repo, text=True).strip()
    worktree = await mgr.checkout_at_sha(sha)
    await mgr.cleanup_worktree(worktree)
    assert not worktree.exists()
