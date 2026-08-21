import asyncio
import logging
from typing import Optional

import httpx

from app.crawler.priority import make_issue

logger = logging.getLogger(__name__)


class LinkChecker:
    def __init__(self, client: httpx.AsyncClient, scan_domain: str):
        self.client = client
        self.scan_domain = scan_domain
        self._internal_cache: dict[str, Optional[int]] = {}
        self._external_cache: dict[str, Optional[int]] = {}

    async def check_links(self, links: list[dict], images: list[dict],
                          page_url: str) -> list[dict]:
        issues = []

        internal = [l for l in links if l.get("is_internal", True)]
        external = [l for l in links if not l.get("is_internal", True)]

        issues.extend(self._check_images(images))

        if external:
            external_issues = await self._check_external_batch(external[:20])
            issues.extend(external_issues)

        issues.extend(self._check_internal_count(internal))

        return issues

    def _check_images(self, images: list[dict]) -> list[dict]:
        issues = []
        for img in images:
            alt = img.get("alt", "")
            src = img.get("src", "")

            if not src:
                continue

            if alt is None or alt.strip() == "":
                issues.append(make_issue("IMG_ALT_EMPTY", f"Image missing alt: {src[:80]}"))

            if not img.get("width") or not img.get("height"):
                issues.append(make_issue("IMG_DIMENSIONS_MISSING", f"Missing dimensions: {src[:80]}"))

        return issues

    async def _check_external_batch(self, links: list[dict]) -> list[dict]:
        issues = []
        tasks = []
        seen = set()

        for link in links:
            href = link.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)
            tasks.append(self._check_one_external(href))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                issues.extend(result)

        return issues

    async def _check_one_external(self, url: str) -> list[dict]:
        if url in self._external_cache:
            status = self._external_cache[url]
            if status and status >= 400:
                return [make_issue("LINK_EXTERNAL_BROKEN", f"HTTP {status}: {url[:100]}")]
            return []

        try:
            resp = await self.client.head(url, follow_redirects=False, timeout=10)
            if resp.status_code in (405, 403, 406, 501):
                resp = await self.client.get(url, follow_redirects=False, timeout=10)
            self._external_cache[url] = resp.status_code
            if resp.status_code >= 400:
                return [make_issue("LINK_EXTERNAL_BROKEN", f"HTTP {resp.status_code}: {url[:100]}")]
            if 300 <= resp.status_code < 400:
                return [make_issue("LINK_EXTERNAL_REDIRECT", f"Redirect {resp.status_code}: {url[:100]}")]
        except httpx.TimeoutException:
            self._external_cache[url] = None
        except httpx.ConnectError:
            self._external_cache[url] = None
        except Exception:
            self._external_cache[url] = None

        return []

    def _check_internal_count(self, links: list[dict]) -> list[dict]:
        if not links:
            return []
        return []

    def mark_internal_result(self, url: str, status_code: Optional[int]):
        self._internal_cache[url] = status_code

    def get_broken_internal(self) -> list[str]:
        return [url for url, status in self._internal_cache.items()
                if status is not None and (status >= 400 or status is None)]
