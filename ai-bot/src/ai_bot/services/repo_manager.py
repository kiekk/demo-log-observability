from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class RepoManagerError(Exception):
    pass


class RepoManager:
    def __init__(self, *, clone_url: str, cache_dir: str, worktree_dir: str, github_token: str | None = None) -> None:
        self._clone_url = clone_url
        self._cache_dir = Path(cache_dir)
        self._worktree_dir = Path(worktree_dir)
        self._bare_path = self._cache_dir / "demo.git"
        self._lock = asyncio.Lock()
        self._github_token = github_token or None  # 빈 문자열은 None 취급

    def _resolve_url(self, url: str) -> str:
        if not self._github_token:
            return url
        # https://github.com/owner/repo.git → https://x-access-token:TOKEN@github.com/owner/repo.git
        prefix = "https://github.com/"
        if url.startswith(prefix):
            return f"https://x-access-token:{self._github_token}@github.com/" + url[len(prefix):]
        return url

    async def ensure_bare_clone(self) -> Path:
        async with self._lock:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._worktree_dir.mkdir(parents=True, exist_ok=True)
            if self._bare_path.exists():
                await self._run(["git", "-C", str(self._bare_path), "fetch", "--all", "--tags", "--prune"])
            else:
                await self._run(["git", "clone", "--bare", self._resolve_url(self._clone_url), str(self._bare_path)])
            return self._bare_path

    async def checkout_at_sha(self, sha: str) -> Path:
        await self.ensure_bare_clone()
        worktree_path = self._worktree_dir / f"wt-{sha[:8]}-{uuid.uuid4().hex[:6]}"
        try:
            await self._run([
                "git", "-C", str(self._bare_path),
                "worktree", "add", "--detach", str(worktree_path), sha,
            ])
        except RepoManagerError as exc:
            raise RepoManagerError(f"failed to checkout {sha}: {exc}") from exc
        return worktree_path

    async def cleanup_worktree(self, worktree_path: Path) -> None:
        if not worktree_path.exists():
            return
        try:
            await self._run([
                "git", "-C", str(self._bare_path),
                "worktree", "remove", "--force", str(worktree_path),
            ])
        except RepoManagerError:
            shutil.rmtree(worktree_path, ignore_errors=True)

    async def _run(self, cmd: list[str]) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RepoManagerError(f"{' '.join(cmd)} failed: {stderr.decode(errors='replace')}")
        return stdout.decode(errors="replace")
