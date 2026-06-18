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

    async def create_pull_request_with_patch(
        self,
        *,
        issue_number: int,
        branch: str,
        title: str,
        body: str,
        labels: list[str],
        patch,  # ai_bot.analyzer.result.Patch
        base_branch: str = "main",
        commit_message: str,
    ) -> PullRequestRef:
        if self._dry_run:
            logger.info("[DRY_RUN] github create_pr: branch=%s title=%s", branch, title)
            return PullRequestRef(number=0, branch=branch, url=f"[dry-run]/{self._repo_full_name}/pull/0")

        def _sync() -> PullRequestRef:
            gh = Github(self._token)
            repo = gh.get_repo(self._repo_full_name)

            # 1. base branch SHA 가져오기
            base_ref = repo.get_git_ref(f"heads/{base_branch}")
            base_sha = base_ref.object.sha

            # 2. 새 브랜치 생성 (이미 존재해도 진행)
            try:
                repo.create_git_ref(ref=f"refs/heads/{branch}", sha=base_sha)
            except Exception as exc:
                logger.warning("create_git_ref %s: %s — using existing", branch, exc)

            # 3. 파일 업데이트
            existing = repo.get_contents(patch.file_path, ref=branch)
            repo.update_file(
                path=patch.file_path,
                message=commit_message,
                content=patch.new_content,
                sha=existing.sha,
                branch=branch,
            )

            # 4. Draft PR
            pr = repo.create_pull(
                title=title,
                body=body,
                base=base_branch,
                head=branch,
                draft=True,
            )

            # 5. 라벨
            if labels:
                pr.add_to_labels(*labels)

            return PullRequestRef(number=pr.number, branch=branch, url=pr.html_url)

        return await asyncio.to_thread(_sync)
