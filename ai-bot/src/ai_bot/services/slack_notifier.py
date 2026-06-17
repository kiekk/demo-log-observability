import logging

import httpx

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, *, webhook_url: str, dry_run: bool = False, timeout_seconds: float = 5.0) -> None:
        self._url = webhook_url
        self._dry_run = dry_run
        self._timeout = timeout_seconds

    async def post(self, text: str) -> None:
        if self._dry_run:
            logger.info("[DRY_RUN] slack post: %s", text)
            return
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, json={"text": text})
            if resp.status_code >= 400:
                logger.warning("slack post failed: status=%s body=%s", resp.status_code, resp.text)
        except httpx.RequestError as exc:
            logger.warning("slack post request error: %s", exc)
