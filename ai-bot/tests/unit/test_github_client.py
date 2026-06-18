from unittest.mock import MagicMock

import pytest

from ai_bot.services.github_client import GitHubClient


@pytest.fixture
def mock_github(mocker) -> MagicMock:
    fake_gh = MagicMock()
    fake_repo = MagicMock()
    fake_repo.full_name = "kiekk/demo-buggy-service"
    fake_issue = MagicMock()
    fake_issue.number = 42
    fake_issue.html_url = "https://github.com/kiekk/demo-buggy-service/issues/42"
    fake_repo.create_issue.return_value = fake_issue
    fake_gh.get_repo.return_value = fake_repo

    mocker.patch("ai_bot.services.github_client.Github", return_value=fake_gh)
    return fake_gh


@pytest.mark.asyncio
async def test_create_issue_returns_number_and_url(mock_github: MagicMock) -> None:
    client = GitHubClient(token="ghp_fake", repo_full_name="kiekk/demo-buggy-service")
    result = await client.create_issue(
        title="[AI] NPE in Foo",
        body="something",
        labels=["ai-incident", "needs-human-review"],
    )
    assert result.number == 42
    assert result.url == "https://github.com/kiekk/demo-buggy-service/issues/42"

    fake_repo = mock_github.get_repo.return_value
    fake_repo.create_issue.assert_called_once_with(
        title="[AI] NPE in Foo",
        body="something",
        labels=["ai-incident", "needs-human-review"],
    )


@pytest.mark.asyncio
async def test_create_issue_dry_run_does_not_call_github(mocker) -> None:
    mock_gh_cls = mocker.patch("ai_bot.services.github_client.Github")
    client = GitHubClient(token="ghp_fake", repo_full_name="x/y", dry_run=True)
    result = await client.create_issue(title="x", body="x", labels=[])
    assert result.number == 0
    mock_gh_cls.return_value.get_repo.assert_not_called()


@pytest.fixture
def mock_github_with_pr(mocker) -> MagicMock:
    fake_gh = MagicMock()
    fake_repo = MagicMock()
    fake_repo.full_name = "kiekk/demo-buggy-service"
    fake_repo.default_branch = "main"

    fake_main_ref = MagicMock()
    fake_main_ref.object.sha = "main-sha"
    fake_repo.get_git_ref.return_value = fake_main_ref

    fake_existing_file = MagicMock()
    fake_existing_file.path = "src/main/kotlin/Foo.kt"
    fake_existing_file.sha = "file-sha-1"
    fake_existing_file.decoded_content = b"fun bar() {}\n"
    fake_repo.get_contents.return_value = fake_existing_file

    fake_repo.update_file.return_value = {"commit": MagicMock(sha="commit-sha")}

    fake_pr = MagicMock()
    fake_pr.number = 99
    fake_pr.html_url = "https://github.com/kiekk/demo-buggy-service/pull/99"
    fake_repo.create_pull.return_value = fake_pr
    fake_pr.add_to_labels = MagicMock()

    fake_gh.get_repo.return_value = fake_repo
    mocker.patch("ai_bot.services.github_client.Github", return_value=fake_gh)
    return fake_gh


@pytest.mark.asyncio
async def test_create_pull_request_with_patch(mock_github_with_pr: MagicMock) -> None:
    from ai_bot.analyzer.result import Patch

    client = GitHubClient(token="ghp_fake", repo_full_name="kiekk/demo-buggy-service")
    pr = await client.create_pull_request_with_patch(
        issue_number=42,
        branch="ai-fix/issue-42",
        title="[AI Fix] #42 - NPE",
        body="fixes NPE",
        labels=["noise-reduction", "human-review-required"],
        patch=Patch(
            file_path="src/main/kotlin/Foo.kt",
            old_content="fun bar() {}\n",
            new_content="fun bar(): Int = 0\n",
        ),
        base_branch="main",
        commit_message="fix: add return value (Fixes #42)",
    )
    assert pr.number == 99
    assert pr.branch == "ai-fix/issue-42"
    assert "pull/99" in pr.url

    fake_repo = mock_github_with_pr.get_repo.return_value
    fake_repo.create_git_ref.assert_called_once_with(ref="refs/heads/ai-fix/issue-42", sha="main-sha")
    fake_repo.update_file.assert_called_once()
    fake_repo.create_pull.assert_called_once()
    create_pull_kwargs = fake_repo.create_pull.call_args.kwargs
    assert create_pull_kwargs["draft"] is True
    assert create_pull_kwargs["base"] == "main"
    assert create_pull_kwargs["head"] == "ai-fix/issue-42"
