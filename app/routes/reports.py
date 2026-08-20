import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import REPORTS_DIR
from app import db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scan/{scan_id}/download")
async def download_report(scan_id: str):
    matches = list(REPORTS_DIR.glob(f"*{scan_id}*.xlsx"))
    if not matches:
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(
        path=str(matches[0]),
        filename=matches[0].name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/scan/{scan_id}/download-partial")
async def download_partial_report(scan_id: str):
    from app.reports.excel import generate_report
    status = db.get_status(scan_id)
    if not status:
        raise HTTPException(status_code=404, detail="Scan not found")
    results = db.get_results(scan_id)
    if not results:
        raise HTTPException(status_code=404, detail="No results yet")
    path = generate_report(scan_id)
    return FileResponse(
        path=path,
        filename=f"sitemap_scan_partial_{scan_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/scan/{scan_id}/summary")
async def scan_summary(scan_id: str):
    status = db.get_status(scan_id)
    if not status:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {
        "error_summary": db.get_error_summary(scan_id),
        "seo_summary": db.get_seo_summary(scan_id),
        "content_summary": db.get_content_summary(scan_id),
        "status_counts": db.count_by_status(scan_id),
    }


@router.get("/scan/{scan_id}/urls")
async def scan_urls(
    scan_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str = Query(""),
    status: str = Query(""),
    issue: str = Query(""),
):
    status_data = db.get_status(scan_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Scan not found")
    offset = (page - 1) * per_page
    results, total = db.get_paginated_results(
        scan_id, offset, per_page, search, status, issue
    )
    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@router.get("/scan/{scan_id}/url/{result_id}")
async def scan_url_detail(scan_id: str, result_id: int):
    result = db.get_url_detail_by_id(scan_id, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="URL not found")
    return result


@router.get("/scan/{scan_id}/issues")
async def scan_issues(scan_id: str):
    status = db.get_status(scan_id)
    if not status:
        raise HTTPException(status_code=404, detail="Scan not found")
    return db.get_all_issues_grouped(scan_id)


@router.get("/search/recent-scans")
async def recent_scans():
    return db.get_recent_scans(limit=10)
