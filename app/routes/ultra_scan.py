import asyncio
import json
import logging
import uuid
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from app.config import DEFAULT_CONCURRENCY, REPORTS_DIR
from app.crawler.sitemap import extract_all_urls
from app.crawler.crawler import AsyncCrawler
from app.reports.ultra_excel import generate_ultra_report

logger = logging.getLogger(__name__)

router = APIRouter()


class UltraScanRequest(BaseModel):
    sitemaps: list[str]
    concurrency: int = 50


@router.post("/ultra-scan")
async def start_ultra_scan(req: UltraScanRequest):
    scan_id = uuid.uuid4().hex[:12]

    async def event_generator():
        start_time = time.monotonic()
        
        # 1. Parse sitemaps and find all URLs
        yield json.dumps({"type": "status", "message": "Fetching and extracting sitemaps..."}) + "\n"
        try:
            urls = await extract_all_urls(scan_id, req.sitemaps)
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Failed to extract sitemaps: {e}"}) + "\n"
            return

        if not urls:
            yield json.dumps({"type": "error", "message": "No valid URLs found in sitemaps."}) + "\n"
            return

        total_urls = len(urls)
        yield json.dumps({"type": "init", "total": total_urls}) + "\n"

        # 2. Run memory-only crawler
        # Create a custom subclass of AsyncCrawler or intercept add_result/update_recent
        crawler = AsyncCrawler(scan_id, total_urls, concurrency=req.concurrency, scan_type="SHORT")
        
        # In-memory list to store all crawl results
        crawled_results = []
        completed_count = 0
        success_count = 0
        redirects_count = 0
        client_errors_count = 0
        server_errors_count = 0

        # We override crawler._check_one to stream results back to event_generator instead of database writes
        # To do this, we intercept and hook into the crawler
        original_check_one = crawler._check_one

        async def hooked_check_one(url, checker, link_checker, robots_info, scan_domain):
            nonlocal completed_count, success_count, redirects_count, client_errors_count, server_errors_count
            
            # Run the actual URL check
            from app.crawler.html_analyzer import analyze_html
            from app.crawler.scorer import compute_score, score_rating
            
            async with crawler.global_semaphore:
                try:
                    result = await checker.check_url(url, fetch_body=True)
                    
                    if result.raw_html and result.status_code and 200 <= result.status_code < 400:
                        try:
                            analysis = analyze_html(result.raw_html, url, scan_domain, short_scan=True)
                            result.title = analysis.get("title", "")
                            result.word_count = analysis.get("word_count", 0)
                            result.issues.extend(analysis.get("issues", []))
                        except Exception:
                            pass
                    
                    result.score = compute_score(result.issues)
                    result.score_rating = score_rating(result.score)
                    result.raw_html = None
                    
                    # Update stats
                    completed_count += 1
                    sc = result.status_code
                    if sc:
                        if 200 <= sc < 300:
                            success_count += 1
                        elif 300 <= sc < 400:
                            redirects_count += 1
                        elif 400 <= sc < 500:
                            client_errors_count += 1
                        elif sc >= 500:
                            server_errors_count += 1
                    else:
                        client_errors_count += 1 # treats network errors/timeouts as client errors in UI stats
                    
                    res_dict = {
                        "url": result.url,
                        "status_code": result.status_code,
                        "final_url": result.final_url,
                        "redirect_count": result.redirect_count,
                        "response_time": result.response_time,
                        "content_length": result.content_length,
                        "title": result.title,
                        "word_count": result.word_count,
                        "error": result.error,
                        "issues": result.issues,
                        "score": result.score,
                    }
                    crawled_results.append(res_dict)
                    
                    # Yield single result
                    yield json.dumps({
                        "type": "result",
                        "data": {
                            "url": result.url[:120],
                            "status": str(result.status_code) if result.status_code else result.error or "N/A",
                            "time": f"{result.response_time:.2f}s",
                            "size": f"{result.content_length // 1024}KB" if result.content_length else "-",
                            "title": (result.title[:50] + "...") if len(result.title) > 50 else (result.title or "-"),
                            "words": str(result.word_count) if result.word_count else "-",
                            "issues": len(result.issues),
                            "score": result.score,
                            "completed": completed_count,
                            "success": success_count,
                            "redirects": redirects_count,
                            "client_errors": client_errors_count,
                            "server_errors": server_errors_count,
                            "percentage": round((completed_count / total_urls * 100), 2)
                        }
                    }) + "\n"
                    
                except Exception as ex:
                    logger.error(f"Error in ultra check: {ex}", exc_info=True)

        # Hook the check_one to capture yields
        # We rewrite crawler.run to execute the hooked_check_one and collect tasks
        async def run_hooked(urls_list):
            nonlocal completed_count
            crawler.global_semaphore = asyncio.Semaphore(crawler.concurrency)
            scan_domain = ""
            if urls_list:
                from app.utils import get_domain
                scan_domain = get_domain(urls_list[0])
            
            from app.config import READ_TIMEOUT, USER_AGENT
            import httpx
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(READ_TIMEOUT),
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            ) as client:
                from app.crawler.http_checker import HTTPChecker
                from app.crawler.link_checker import LinkChecker
                from app.crawler.robots import fetch_robots
                
                checker = HTTPChecker(client)
                link_checker = LinkChecker(client, scan_domain)
                robots_info = await fetch_robots(f"https://{scan_domain}")
                
                batch_size = 100
                for i in range(0, len(urls_list), batch_size):
                    batch = urls_list[i:i + batch_size]
                    tasks = []
                    for url in batch:
                        tasks.append(hooked_check_one(url, checker, link_checker, robots_info, scan_domain))
                    
                    # Since hooked_check_one is a generator, we process each as they complete
                    if tasks:
                        # We run tasks concurrently and read values
                        async def run_gen(gen):
                            async for val in gen:
                                yield val
                        
                        # Merge streams
                        async def merge_streams(*generators):
                            queue = asyncio.Queue()
                            loop = asyncio.get_event_loop()
                            
                            async def worker(g):
                                try:
                                    async for item in g:
                                        await queue.put(item)
                                except Exception as err:
                                    logger.error(f"Worker generator error: {err}")
                            
                            workers = [asyncio.create_task(worker(g)) for g in generators]
                            
                            # Wait for all workers to finish and feed the queue
                            async def monitor():
                                await asyncio.gather(*workers)
                                await queue.put(None) # Sentinel
                            
                            asyncio.create_task(monitor())
                            
                            while True:
                                item = await queue.get()
                                if item is None:
                                    break
                                yield item
                        
                        async for event_val in merge_streams(*tasks):
                            yield event_val

        # Execute hooked crawl and stream chunks
        async for chunk in run_hooked(urls):
            yield chunk

        # 3. Generate excel report on finished crawl results
        yield json.dumps({"type": "status", "message": "Generating Excel report..."}) + "\n"
        elapsed_time = time.monotonic() - start_time
        
        try:
            report_filepath = generate_ultra_report(scan_id, crawled_results, elapsed_time, req.sitemaps)
            yield json.dumps({
                "type": "complete",
                "download_url": f"/api/ultra-scan/download/{scan_id}",
                "total": len(crawled_results),
                "success": success_count,
                "redirects": redirects_count,
                "client_errors": client_errors_count,
                "server_errors": server_errors_count,
                "elapsed": round(elapsed_time, 2)
            }) + "\n"
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"Failed to generate report: {e}"}) + "\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/ultra-scan/download/{scan_id}")
async def download_ultra_report(scan_id: str):
    matches = list(REPORTS_DIR.glob(f"*ultra*_{scan_id}.xlsx"))
    if not matches:
        raise HTTPException(status_code=404, detail="Ultra report not found")
    return FileResponse(
        path=str(matches[0]),
        filename=matches[0].name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
