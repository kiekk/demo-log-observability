import pytest
import respx
from httpx import Response

from ai_bot.services.slack_notifier import SlackNotifier


@pytest.mark.asyncio
@respx.mock
async def test_post_message_sends_correct_payload() -> None:
    route = respx.post("https://hooks.slack.com/services/X").mock(return_value=Response(200, text="ok"))
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/X")
    await notifier.post("Hello :wave:")
    assert route.called
    call = route.calls[-1]
    body = call.request.content.decode()
    assert "Hello :wave:" in body


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_does_not_send() -> None:
    route = respx.post("https://hooks.slack.com/services/X").mock(return_value=Response(200, text="ok"))
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/X", dry_run=True)
    await notifier.post("Should not send")
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_failure_does_not_raise() -> None:
    respx.post("https://hooks.slack.com/services/X").mock(return_value=Response(500))
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/services/X")
    await notifier.post("test")
