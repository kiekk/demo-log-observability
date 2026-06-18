from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from github import Github

logger = logging.getLogger(__name__)


@dataclass
class IssueRef:
    number: int
    url: str


@dataclass
class PullRequestRef:
    number: int
    url: str
    branch: str


class GitHubClient:
    def __init__(
        self,
        *,
        token: str,
        repo_full_name: str,
        dry_run: bool = False,
    ) -> None:
        self._token = token
        self._repo_full_name = repo_full_name
        self._dry_run = dry_run

    async def create_issue(self, *, title: str, body: str, labels: list[str]) -> IssueRef:
        if self._dry_run:
            logger.info("[DRY_RUN] github create_issue: title=%s", title)
            return IssueRef(number=0, url=f"[dry-run]/{self._repo_full_name}/issues/0")

        def _sync() -> IssueRef:
            gh = Github(self._token)
            repo = gh.get_repo(self._repo_full_name)
            issue = repo.create_issue(title=title, body=body, labels=labels)
            return IssueRef(number=issue.number, url=issue.html_url)

        return await asyncio.to_thread(_sync)
