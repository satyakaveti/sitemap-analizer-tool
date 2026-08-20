import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.scan_models import ScanState, ScanStatus
from app.config import DEFAULT_CONCURRENCY

router = APIRouter()

scans: dict[str, ScanState] = {}


class ScanRequest(BaseModel):
    sitemaps: list[str]
    concurrency: int = DEFAULT_CONCURRENCY


@router.post("/scan")
async def start_scan(req: ScanRequest):
    scan_id = uuid.uuid4().hex[:12]
    state = ScanState(
        scan_id=scan_id,
        sitemaps=req.sitemaps,
    )
    scans[scan_id] = state
    asyncio.create_task(_run_scan(scan_id, state))
    return {"scan_id": scan_id, "status": "QUEUED"}


@router.get("/scan/{scan_id}/status")
async def scan_status(scan_id: str):
    if scan_id not in scans:
        raise HTTPException(status_code=404, detail="Scan not found")
    s = scans[scan_id]
    elapsed = s.elapsed_seconds
    completed = s.completed
    total = s.total_urls
    eta = None
    if completed > 0 and total > 0 and s.status == ScanStatus.RUNNING:
        rate = completed / elapsed if elapsed > 0 else 0
        remaining = total - completed
        eta = remaining / rate if rate > 0 else None
    return {
        "scan_id": s.scan_id,
        "status": s.status.value,
        "total": s.total_urls,
        "completed": s.completed,
        "success": s.success,
        "redirects": s.redirects,
        "client_errors": s.client_errors,
        "server_errors": s.server_errors,
        "timeouts": s.timeouts,
        "dns_errors": s.dns_errors,
        "ssl_errors": s.ssl_errors,
        "other_errors": s.other_errors,
        "seo_issues": s.seo_issues,
        "content_issues": s.content_issues,
        "percentage": s.percentage,
        "elapsed": round(elapsed, 1),
        "eta": round(eta, 1) if eta else None,
        "error": s.error,
        "report_path": s.report_path,
        "current_url": s.current_url,
        "recent_results": s.recent_results,
    }


@router.post("/scan/{scan_id}/cancel")
async def cancel_scan(scan_id: str):
    if scan_id not in scans:
        raise HTTPException(status_code=404, detail="Scan not found")
    scans[scan_id].is_cancelled = True
    return {"status": "CANCELLED"}


async def _run_scan(scan_id: str, state: ScanState):
    from app.crawler.sitemap import extract_all_urls
    from app.crawler.crawler import AsyncCrawler
    from app.reports.excel import generate_report

    try:
        state.status = ScanStatus.RUNNING
        state.started_at = datetime.utcnow()

        urls = await extract_all_urls(state.sitemaps, state)
        if state.is_cancelled:
            state.status = ScanStatus.CANCELLED
            return
        if not urls:
            state.status = ScanStatus.FAILED
            state.error = "No valid URLs found in sitemaps"
            return

        state.total_urls = len(urls)

        crawler = AsyncCrawler(state)
        await crawler.run(urls)

        if state.is_cancelled:
            state.status = ScanStatus.CANCELLED
            return

        for r in state.results:
            if r.status_code and r.status_code >= 400:
                if r.status_code < 500:
                    state.client_errors += 1
                else:
                    state.server_errors += 1
            elif r.redirect_count > 0:
                state.redirects += 1
            elif r.error:
                if "timeout" in r.error.lower():
                    state.timeouts += 1
                elif "dns" in r.error.lower():
                    state.dns_errors += 1
                elif "ssl" in r.error.lower():
                    state.ssl_errors += 1
                else:
                    state.other_errors += 1
            else:
                state.success += 1

            seo = sum(1 for i in r.issues if any(k in i.lower() for k in ["title", "meta", "h1", "canonical", "noindex", "nofollow"]))
            content = sum(1 for i in r.issues if any(k in i.lower() for k in ["thin", "soft", "word", "error"]))
            state.seo_issues += seo
            state.content_issues += content

        report_path = generate_report(state)
        state.report_path = report_path

        state.status = ScanStatus.COMPLETED
        state.completed_at = datetime.utcnow()

    except Exception as e:
        state.status = ScanStatus.FAILED
        state.error = str(e)
        state.completed_at = datetime.utcnow()
