import pytest
import respx
from httpx import Response

from ai_bot.services.log_fetcher import LogFetcher, LogLine


@pytest.mark.asyncio
@respx.mock
async def test_fetch_by_commit_sha_returns_log_lines() -> None:
    sample_response = {
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"service": "demo-buggy-service", "level": "ERROR"},
                    "values": [
                        ["1718600000000000000", '{"timestamp":"2026-06-17T12:00:00Z","message":"NPE here","level":"ERROR","exception_class":"NullPointerException","request_id":"r-1"}'],
                        ["1718600001000000000", '{"timestamp":"2026-06-17T12:00:01Z","message":"another error","level":"ERROR","exception_class":"NullPointerException","request_id":"r-2"}'],
                    ],
                }
            ],
        }
    }
    respx.get("http://loki:3100/loki/api/v1/query_range").mock(return_value=Response(200, json=sample_response))

    fetcher = LogFetcher(loki_url="http://loki:3100")
    lines = await fetcher.fetch_recent_errors(service="demo-buggy-service", commit_sha="abc123", window_minutes=10)

    assert len(lines) == 2
    assert all(isinstance(line, LogLine) for line in lines)
    assert lines[0].exception_class == "NullPointerException"
    assert lines[0].request_id == "r-1"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_empty_on_no_results() -> None:
    respx.get("http://loki:3100/loki/api/v1/query_range").mock(
        return_value=Response(200, json={"data": {"result": []}})
    )
    fetcher = LogFetcher(loki_url="http://loki:3100")
    lines = await fetcher.fetch_recent_errors(service="x", commit_sha="y", window_minutes=10)
    assert lines == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_handles_loki_error() -> None:
    respx.get("http://loki:3100/loki/api/v1/query_range").mock(return_value=Response(500))
    fetcher = LogFetcher(loki_url="http://loki:3100")
    lines = await fetcher.fetch_recent_errors(service="x", commit_sha="y", window_minutes=10)
    assert lines == []
