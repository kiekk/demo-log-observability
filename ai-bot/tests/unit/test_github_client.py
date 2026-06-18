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
