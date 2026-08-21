import asyncio
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.scan_models import ScanStatus
from app.config import DEFAULT_CONCURRENCY
from app import db

logger = logging.getLogger(__name__)

router = APIRouter()


class ScanRequest(BaseModel):
    sitemaps: list[str]
    concurrency: int = DEFAULT_CONCURRENCY


@router.post("/scan")
async def start_scan(req: ScanRequest):
    scan_id = uuid.uuid4().hex[:12]
    db.create_scan(scan_id, req.sitemaps)
    task = asyncio.create_task(_run_scan(scan_id, req.sitemaps))
    task.add_done_callback(lambda t: _task_done(scan_id, t))
    return {"scan_id": scan_id, "status": "QUEUED"}


def _task_done(scan_id: str, task: asyncio.Task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error(f"scan={scan_id} background task crashed: {exc}", exc_info=exc)
        try:
            db.update_scan(scan_id, status="FAILED", error=str(exc),
                          completed_at=datetime.utcnow().isoformat())
        except Exception:
            pass


@router.get("/scan/{scan_id}/status")
async def scan_status(scan_id: str):
    data = db.get_status(scan_id)
    if not data:
        raise HTTPException(status_code=404, detail="Scan not found")
    return data


@router.post("/scan/{scan_id}/cancel")
async def cancel_scan(scan_id: str):
    data = db.get_status(scan_id)
    if not data:
        raise HTTPException(status_code=404, detail="Scan not found")
    db.update_scan(scan_id, is_cancelled=1)
    return {"status": "CANCELLED"}


async def _run_scan(scan_id: str, sitemaps: list[str]):
    from app.crawler.sitemap import extract_all_urls
    from app.crawler.crawler import AsyncCrawler
    from app.reports.excel import generate_report

    try:
        db.update_scan(scan_id, status="RUNNING", phase="Fetching sitemaps")
        logger.info(f"scan={scan_id} phase=fetching_sitemaps sitemaps={sitemaps}")

        urls = await extract_all_urls(scan_id, sitemaps)
        status = db.get_status(scan_id)
        if status and status["is_cancelled"]:
            db.update_scan(scan_id, status="CANCELLED")
            return
        if not urls:
            db.update_scan(scan_id, status="FAILED", error="No valid URLs found in sitemaps",
                          completed_at=datetime.utcnow().isoformat())
            return

        db.update_scan(scan_id, total_urls=len(urls), phase="Crawling URLs")
        logger.info(f"scan={scan_id} phase=crawling urls_found={len(urls)}")

        crawler = AsyncCrawler(scan_id, len(urls))
        await crawler.run(urls)

        status = db.get_status(scan_id)
        if status and status["is_cancelled"]:
            db.update_scan(scan_id, status="CANCELLED")
            return

        report_path = generate_report(scan_id)
        db.update_scan(scan_id, report_path=report_path, status="COMPLETED",
                      completed_at=datetime.utcnow().isoformat())
        logger.info(f"scan={scan_id} phase=completed")

    except Exception as e:
        logger.error(f"scan={scan_id} failed: {e}")
        db.update_scan(scan_id, status="FAILED", error=str(e),
                      completed_at=datetime.utcnow().isoformat())
