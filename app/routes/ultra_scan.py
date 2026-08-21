import asyncio
import json
import logging
import uuid
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
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


def read_last_n_lines(filepath: Path, n: int = 15) -> list[dict]:
    try:
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in deque(f, n)]
    except Exception as e:
        logger.error(f"Error reading last {n} lines from {filepath}: {e}")
        return []


def read_all_jsonl(filepath: Path) -> list[dict]:
    results = []
    try:
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
    except Exception as e:
        logger.error(f"Error reading all lines from {filepath}: {e}")
    return results


async def _run_ultra_crawl(scan_id: str, urls: list[str], concurrency: int, sitemaps: list[str]):
    status_filepath = REPORTS_DIR / f"ultra_status_{scan_id}.json"
    results_filepath = REPORTS_DIR / f"ultra_results_{scan_id}.jsonl"
    
    start_time = time.monotonic()
    total_urls = len(urls)
    
    status_data = {
        "status": "RUNNING",
        "sitemaps": sitemaps,
        "total": total_urls,
        "completed": 0,
        "success": 0,
        "redirects": 0,
        "client_errors": 0,
        "server_errors": 0,
        "elapsed": 0,
        "eta": None,
        "phase": "Crawling URLs...",
        "current_url": "-"
    }
    
    def save_status():
        try:
            status_data["elapsed"] = int(time.monotonic() - start_time)
            # Calculate simple ETA
            comp = status_data["completed"]
            if comp > 0 and comp < total_urls:
                rate = comp / status_data["elapsed"] if status_data["elapsed"] > 0 else 1
                status_data["eta"] = int((total_urls - comp) / rate)
            else:
                status_data["eta"] = None
            
            with open(status_filepath, "w", encoding="utf-8") as sf:
                json.dump(status_data, sf)
        except Exception as e:
            logger.error(f"Error saving status for {scan_id}: {e}")

    save_status()

    crawler = AsyncCrawler(scan_id, total_urls, concurrency=concurrency, scan_type="SHORT")
    crawler.global_semaphore = asyncio.Semaphore(crawler.concurrency)

    scan_domain = ""
    if urls:
        from app.utils import get_domain
        scan_domain = get_domain(urls[0])

    from app.config import READ_TIMEOUT, USER_AGENT
    import httpx
    
    async def process_one(url, checker, link_checker, robots_info):
        from app.crawler.html_analyzer import analyze_html
        from app.crawler.scorer import compute_score, score_rating
        
        async with crawler.global_semaphore:
            status_data["current_url"] = url[:200]
            save_status()

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
                status_data["completed"] += 1
                sc = result.status_code
                if sc:
                    if 200 <= sc < 300:
                        status_data["success"] += 1
                    elif 300 <= sc < 400:
                        status_data["redirects"] += 1
                    elif 400 <= sc < 500:
                        status_data["client_errors"] += 1
                    elif sc >= 500:
                        status_data["server_errors"] += 1
                else:
                    status_data["client_errors"] += 1
                
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
                
                # Append line to local JSONL
                with open(results_filepath, "a", encoding="utf-8") as rf:
                    rf.write(json.dumps(res_dict) + "\n")
                
                save_status()
                
            except Exception as ex:
                logger.error(f"Error checking {url} in ultra scan: {ex}", exc_info=True)

    try:
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
            for i in range(0, len(urls), batch_size):
                batch = urls[i:i + batch_size]
                tasks = [process_one(u, checker, link_checker, robots_info) for u in batch]
                await asyncio.gather(*tasks)

        status_data["status"] = "COMPLETED"
        status_data["phase"] = "Scan completed!"
        status_data["current_url"] = "-"
        save_status()

    except Exception as err:
        logger.error(f"Ultra crawl failed for {scan_id}: {err}", exc_info=True)
        status_data["status"] = "FAILED"
        status_data["phase"] = f"Failed: {err}"
        save_status()


@router.post("/ultra-scan")
async def start_ultra_scan(req: UltraScanRequest, background_tasks: BackgroundTasks):
    scan_id = uuid.uuid4().hex[:12]
    
    # 1. Parse sitemaps
    try:
        urls = await extract_all_urls(scan_id, req.sitemaps)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract sitemaps: {e}")

    if not urls:
        raise HTTPException(status_code=400, detail="No URLs found in the sitemaps.")

    # Write initial running status
    status_filepath = REPORTS_DIR / f"ultra_status_{scan_id}.json"
    with open(status_filepath, "w", encoding="utf-8") as sf:
        json.dump({
            "status": "RUNNING",
            "sitemaps": req.sitemaps,
            "total": len(urls),
            "completed": 0,
            "success": 0,
            "redirects": 0,
            "client_errors": 0,
            "server_errors": 0,
            "elapsed": 0,
            "eta": None,
            "phase": "Starting scan...",
            "current_url": "-"
        }, sf)

    # Spawn background task
    background_tasks.add_task(_run_ultra_crawl, scan_id, urls, req.concurrency, req.sitemaps)

    return {"scan_id": scan_id}


@router.get("/ultra-scan/{scan_id}/status")
async def get_ultra_scan_status(scan_id: str):
    status_filepath = REPORTS_DIR / f"ultra_status_{scan_id}.json"
    results_filepath = REPORTS_DIR / f"ultra_results_{scan_id}.jsonl"

    if not status_filepath.exists():
        raise HTTPException(status_code=404, detail="Ultra scan status not found.")

    try:
        with open(status_filepath, "r", encoding="utf-8") as sf:
            status = json.load(sf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read status: {e}")

    # Read last 15 results for live dashboard table rendering
    raw_recent = read_last_n_lines(results_filepath, 15)
    recent_results = []
    for r in raw_recent:
        sc = r.get("status_code")
        recent_results.append({
            "url": r.get("url", "")[:120],
            "status": str(sc) if sc else r.get("error") or "N/A",
            "time": f"{r.get('response_time', 0):.2f}s",
            "size": f"{r.get('content_length', 0) // 1024}KB" if r.get('content_length') else "-",
            "title": (r.get("title", "")[:50] + "...") if len(r.get("title", "")) > 50 else (r.get("title", "") or "-"),
            "words": str(r.get("word_count", "-")),
            "issues": len(r.get("issues", [])),
            "score": r.get("score", 100)
        })

    status["recent_results"] = recent_results
    status["percentage"] = round((status["completed"] / status["total"] * 100), 2) if status["total"] > 0 else 0
    return status


@router.get("/ultra-scan/download/{scan_id}")
async def download_ultra_report(scan_id: str):
    status_filepath = REPORTS_DIR / f"ultra_status_{scan_id}.json"
    results_filepath = REPORTS_DIR / f"ultra_results_{scan_id}.jsonl"

    if not status_filepath.exists() or not results_filepath.exists():
        raise HTTPException(status_code=404, detail="Ultra report results not found")

    try:
        with open(status_filepath, "r", encoding="utf-8") as sf:
            status = json.load(sf)
    except Exception:
        status = {}

    results = read_all_jsonl(results_filepath)
    if not results:
        raise HTTPException(status_code=400, detail="No crawled URLs found to generate report.")

    try:
        # Build Excel sheet on demand in separate request
        report_filepath = generate_ultra_report(
            scan_id,
            results,
            status.get("elapsed", 0),
            status.get("sitemaps", [])
        )
        return FileResponse(
            path=report_filepath,
            filename=Path(report_filepath).name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Excel report: {e}")


@router.get("/ultra-scan/recent")
async def get_recent_ultra_scans():
    files = list(REPORTS_DIR.glob("ultra_status_*.json"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    recent = []
    for f in files[:10]: # Limit to last 10 scans
        try:
            scan_id = f.name.replace("ultra_status_", "").replace(".json", "")
            with open(f, "r", encoding="utf-8") as sf:
                data = json.load(sf)
            recent.append({
                "scan_id": scan_id,
                "sitemaps": data.get("sitemaps", []),
                "total": data.get("total", 0),
                "completed": data.get("completed", 0),
                "status": data.get("status", "UNKNOWN"),
                "date": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception:
            pass
    return recent
