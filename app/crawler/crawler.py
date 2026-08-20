import asyncio
import logging

import httpx

from app.config import USER_AGENT, CONNECT_TIMEOUT, READ_TIMEOUT, DEFAULT_CONCURRENCY

logger = logging.getLogger(__name__)


class AsyncCrawler:
    def __init__(self, state):
        self.state = state
        self.global_semaphore = None

    async def run(self, urls: list[str]):
        self.global_semaphore = asyncio.Semaphore(DEFAULT_CONCURRENCY)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT,
                read=READ_TIMEOUT,
            ),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=DEFAULT_CONCURRENCY,
                max_keepalive_connections=DEFAULT_CONCURRENCY,
            ),
        ) as client:
            from app.crawler.http_checker import HTTPChecker
            checker = HTTPChecker(client)
            batch_size = 100

            for i in range(0, len(urls), batch_size):
                if self.state.is_cancelled:
                    break

                batch = urls[i:i + batch_size]
                tasks = []
                for url in batch:
                    if self.state.is_cancelled:
                        break
                    tasks.append(self._check_one(url, checker, client))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_one(self, url: str, checker, client):
        from app.crawler.html_analyzer import analyze_html

        async with self.global_semaphore:
            if self.state.is_cancelled:
                return

            result = await checker.check_url(url)

            if result.status_code and 200 <= result.status_code < 400:
                try:
                    if result.final_url and result.final_url != url:
                        result.issues.append(f"Sitemap URL redirects to {result.final_url}")

                    resp = await client.get(
                        result.final_url or url,
                        follow_redirects=False,
                    )
                    html = resp.content
                    analysis = analyze_html(html, url)
                    result.title = analysis.get("title", "")
                    result.title_length = analysis.get("title_length", 0)
                    result.meta_description = analysis.get("meta_description", "")
                    result.meta_description_length = analysis.get("meta_description_length", 0)
                    result.h1 = analysis.get("h1", "")
                    result.h1_count = analysis.get("h1_count", 0)
                    result.word_count = analysis.get("word_count", 0)
                    result.canonical = analysis.get("canonical", "")
                    result.robots = analysis.get("robots", "")
                    result.indexable = analysis.get("indexable", True)
                    result.issues.extend(analysis.get("issues", []))
                except Exception:
                    pass

            self.state.results.append(result)
            self.state.completed += 1
