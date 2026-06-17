from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LogLine:
    timestamp_ns: int
    message: str
    level: str
    exception_class: str | None
    request_id: str | None
    raw: dict


class LogFetcher:
    def __init__(self, loki_url: str, timeout_seconds: float = 10.0) -> None:
        self._loki_url = loki_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch_recent_errors(
        self, *, service: str, commit_sha: str, window_minutes: int, limit: int = 50,
    ) -> list[LogLine]:
        end_ns = int(time.time() * 1_000_000_000)
        start_ns = end_ns - window_minutes * 60 * 1_000_000_000
        query = (
            f'{{service="{service}"}} | json '
            f'| commit_sha="{commit_sha}" | level="ERROR"'
        )
        params = {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": str(limit),
            "direction": "backward",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._loki_url}/loki/api/v1/query_range", params=params)
            if resp.status_code != 200:
                logger.warning("Loki returned %s — falling back to empty log context", resp.status_code)
                return []
            data = resp.json().get("data", {})
            return _parse_streams(data.get("result", []))
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("Loki request failed: %s — empty log context", exc)
            return []


def _parse_streams(streams: list[dict]) -> list[LogLine]:
    lines: list[LogLine] = []
    for stream in streams:
        for ts_str, raw_line in stream.get("values", []):
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            lines.append(
                LogLine(
                    timestamp_ns=int(ts_str),
                    message=parsed.get("message", ""),
                    level=parsed.get("level", "UNKNOWN"),
                    exception_class=parsed.get("exception_class"),
                    request_id=parsed.get("request_id"),
                    raw=parsed,
                )
            )
    lines.sort(key=lambda x: x.timestamp_ns)
    return lines
