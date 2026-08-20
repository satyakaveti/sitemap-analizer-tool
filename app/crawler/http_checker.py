import asyncio
import logging
import time
from typing import Optional

import httpx

from app.config import (
    CONNECT_TIMEOUT, READ_TIMEOUT, MAX_REDIRECTS,
    RETRY_COUNT, RETRY_BACKOFF, RETRY_STATUSES, NO_RETRY_STATUSES,
    USER_AGENT, PER_HOST_CONCURRENCY, MAX_HTML_PARSE_SIZE,
)
from app.models.scan_models import URLResult
from app.utils import get_domain

logger = logging.getLogger(__name__)

host_semaphores: dict[str, asyncio.Semaphore] = {}


def get_host_semaphore(host: str) -> asyncio.Semaphore:
    if host not in host_semaphores:
        host_semaphores[host] = asyncio.Semaphore(PER_HOST_CONCURRENCY)
    return host_semaphores[host]


class HTTPChecker:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def check_url(self, url: str, fetch_body: bool = False) -> URLResult:
        result = URLResult(url=url)
        host = get_domain(url)
        sem = get_host_semaphore(host)

        async with sem:
            for attempt in range(1 + RETRY_COUNT):
                try:
                    start = time.monotonic()
                    resp = await self.client.get(
                        url,
                        follow_redirects=True,
                    )
                    elapsed = time.monotonic() - start

                    result.status_code = resp.status_code
                    result.final_url = str(resp.url)
                    result.redirect_count = len(resp.history)
                    result.response_time = round(elapsed, 3)
                    result.content_type = resp.headers.get("content-type", "")
                    result.content_length = int(resp.headers.get("content-length", 0))

                    if resp.history:
                        result.redirect_chain = [str(r.url) for r in resp.history]

                    if fetch_body and 200 <= resp.status_code < 400:
                        result.raw_html = resp.content[:MAX_HTML_PARSE_SIZE]

                    if resp.status_code in RETRY_STATUSES and attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue

                    return result

                except httpx.TimeoutException:
                    result.error = "timeout"
                    if attempt < RETRY_COUNT:
                        await asyncio.sleep(RETRY_BACKOFF[attempt])
                        continue
                    return result

                except httpx.ConnectError as e:
                    err_str = str(e).lower()
                    if "dns" in err_str or "resolve" in err_str:
                        result.error = f"dns_error: {e}"
                    elif "ssl" in err_str or "certificate" in err_str:
                        result.error = f"ssl_error: {e}"
                    else:
                        result.error = f"connection_error: {e}"
                    return result

                except Exception as e:
                    result.error = f"error: {e}"
                    return result

        return result
