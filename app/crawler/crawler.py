import asyncio
import logging

import httpx

from app.config import USER_AGENT, CONNECT_TIMEOUT, READ_TIMEOUT, DEFAULT_CONCURRENCY
from app.crawler.priority import has_critical, has_high
from app.crawler.scorer import compute_score, score_rating
from app.utils import get_domain

logger = logging.getLogger(__name__)


class AsyncCrawler:
    def __init__(self, scan_id: str, total_urls: int, concurrency: int = DEFAULT_CONCURRENCY, scan_type: str = "FULL"):
        self.scan_id = scan_id
        self.total_urls = total_urls
        self.scan_type = scan_type.upper()
        if self.scan_type == "SHORT":
            self.concurrency = min(concurrency or 50, 100)
        else:
            from app.config import MAX_CONCURRENCY
            self.concurrency = min(concurrency, MAX_CONCURRENCY)
        self.global_semaphore = None
        self._completed = 0

    async def run(self, urls: list[str]):
        self.global_semaphore = asyncio.Semaphore(self.concurrency)

        scan_domain = get_domain(urls[0]) if urls else ""

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(READ_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        ) as client:

            from app.crawler.http_checker import HTTPChecker
            from app.crawler.link_checker import LinkChecker
            from app.crawler.robots import fetch_robots
            from app import db

            checker = HTTPChecker(client)
            link_checker = LinkChecker(client, scan_domain)
            robots_info = await fetch_robots(f"https://{scan_domain}")
            batch_size = 100

            for i in range(0, len(urls), batch_size):
                db_status = db.get_status(self.scan_id)
                if db_status and db_status["is_cancelled"]:
                    logger.info(f"[scan={self.scan_id}] Crawler cancelled before batch starting at index {i}")
                    break

                batch = urls[i:i + batch_size]
                logger.info(f"[scan={self.scan_id}] Starting crawl batch from index {i} with {len(batch)} URLs")
                tasks = []
                for url in batch:
                    tasks.append(self._check_one(url, checker, link_checker, robots_info, scan_domain))

                if tasks:
                    logger.info(f"[scan={self.scan_id}] Gathering {len(tasks)} tasks for batch starting at {i}")
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.info(f"[scan={self.scan_id}] Completed batch starting at index {i}")


    async def _check_one(self, url: str, checker, link_checker, robots_info, scan_domain):
        from app.crawler.html_analyzer import analyze_html
        from app.crawler.url_analyzer import analyze_url
        from app.crawler.structured_data import analyze_structured_data
        from app.crawler.robots import evaluate_robots
        from app import db

        logger.info(f"[scan={self.scan_id}] Entering _check_one for {url}")
        try:
            async with self.global_semaphore:
                logger.info(f"[scan={self.scan_id}] Acquired global semaphore for {url}")
                db_status = db.get_status(self.scan_id)
                if db_status and db_status["is_cancelled"]:
                    logger.info(f"[scan={self.scan_id}] Scan is cancelled, skipping {url}")
                    return

                db.update_scan(self.scan_id, current_url=url[:200])

                logger.info(f"[scan={self.scan_id}] Fetching page via checker: {url}")
                result = await checker.check_url(url, fetch_body=True)
                logger.info(f"[scan={self.scan_id}] Fetched {url} - Status Code: {result.status_code}, Error: {result.error}")

                if result.raw_html and result.status_code and 200 <= result.status_code < 400:
                    try:
                        logger.info(f"[scan={self.scan_id}] Parsing HTML for {url}")
                        analysis = analyze_html(result.raw_html, url, scan_domain, short_scan=(self.scan_type == "SHORT"))
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
                        result.internal_link_count = analysis.get("internal_link_count", 0)
                        result.external_link_count = analysis.get("external_link_count", 0)
                        result.image_count = analysis.get("image_count", 0)
                        result.image_no_alt_count = analysis.get("image_no_alt_count", 0)

                        if self.scan_type != "SHORT":
                            result.issues.extend(analysis.get("issues", []))
                            links = analysis.get("links", [])
                            images = analysis.get("images", [])

                            logger.info(f"[scan={self.scan_id}] Checking external links/images for {url}")
                            link_issues = await link_checker.check_links(links, images, url)
                            result.issues.extend(link_issues)

                            logger.info(f"[scan={self.scan_id}] Parsing structured data for {url}")
                            sd_issues = analyze_structured_data(result.raw_html)
                            result.issues.extend(sd_issues)
                        else:
                            # Filter issues list for SHORT scan to only keep content threshold violations
                            content_issue_codes = {"CONTENT_THIN", "CONTENT_VERY_THIN"}
                            analysis_issues = [iss for iss in analysis.get("issues", []) if iss.get("code") in content_issue_codes]
                            result.issues.extend(analysis_issues)

                    except Exception as e:
                        logger.error(f"[scan={self.scan_id}] HTML analysis failed for {url}: {e}", exc_info=True)

                if self.scan_type != "SHORT":
                    logger.info(f"[scan={self.scan_id}] Running URL and robots checks for {url}")
                    url_issues = analyze_url(url, scan_domain)
                    result.issues.extend(url_issues)

                    robots_issues = evaluate_robots(url, robots_info)
                    result.issues.extend(robots_issues)

                result.score = compute_score(result.issues)
                result.score_rating = score_rating(result.score)

                result.raw_html = None
                self._completed += 1

                logger.info(f"[scan={self.scan_id}] Saving result to DB for {url}")
                db.add_result(self.scan_id, {
                    "url": result.url,
                    "status_code": result.status_code,
                    "final_url": result.final_url,
                    "redirect_count": result.redirect_count,
                    "redirect_chain": result.redirect_chain,
                    "response_time": result.response_time,
                    "content_type": result.content_type,
                    "content_length": result.content_length,
                    "title": result.title,
                    "title_length": result.title_length,
                    "meta_description": result.meta_description,
                    "meta_description_length": result.meta_description_length,
                    "h1": result.h1,
                    "h1_count": result.h1_count,
                    "word_count": result.word_count,
                    "canonical": result.canonical,
                    "robots": result.robots,
                    "indexable": result.indexable,
                    "error": result.error,
                    "issues": result.issues,
                    "score": result.score,
                    "internal_link_count": result.internal_link_count,
                    "external_link_count": result.external_link_count,
                    "broken_link_count": result.broken_link_count,
                    "image_count": result.image_count,
                    "image_no_alt_count": result.image_no_alt_count,
                })

                logger.info(f"[scan={self.scan_id}] Saving recent entries for {url}")
                db.update_recent(self.scan_id, {
                    "url": result.url[:120],
                    "status": str(result.status_code) if result.status_code else result.error or "N/A",
                    "time": f"{result.response_time:.2f}s",
                    "size": f"{result.content_length // 1024}KB" if result.content_length else "-",
                    "title": (result.title[:50] + "...") if len(result.title) > 50 else (result.title or "-"),
                    "words": str(result.word_count) if result.word_count else "-",
                    "issues": len(result.issues),
                    "score": result.score,
                })

                logger.info(f"[scan={self.scan_id}] Incrementing stats counters for {url}")
                if result.status_code and result.status_code >= 400:
                    field = "client_errors" if result.status_code < 500 else "server_errors"
                    db.increment_scan(self.scan_id, field)
                elif result.redirect_count > 0:
                    db.increment_scan(self.scan_id, "redirects")
                elif result.error:
                    if "timeout" in result.error.lower():
                        db.increment_scan(self.scan_id, "timeouts")
                    elif "dns" in result.error.lower():
                        db.increment_scan(self.scan_id, "dns_errors")
                    elif "ssl" in result.error.lower():
                        db.increment_scan(self.scan_id, "ssl_errors")
                    else:
                        db.increment_scan(self.scan_id, "other_errors")
                else:
                    db.increment_scan(self.scan_id, "success")

                if has_critical(result.issues) or has_high(result.issues):
                    db.increment_scan(self.scan_id, "seo_issues")

                content_codes = ["CONTENT_THIN", "CONTENT_VERY_THIN", "SOFT_404", "APP_ERROR"]
                if any(any(code in issue.get("code", "") for code in content_codes) for issue in result.issues):
                    db.increment_scan(self.scan_id, "content_issues")

                db.increment_scan(self.scan_id, "completed")
                logger.info(f"[scan={self.scan_id}] Successfully finished _check_one for {url}")

                if self._completed % 50 == 0:
                    logger.info(f"scan={self.scan_id} completed={self._completed}/{self.total_urls}")

        except Exception as e:
            logger.error(f"[scan={self.scan_id}] FATAL exception inside _check_one for {url}: {e}", exc_info=True)
