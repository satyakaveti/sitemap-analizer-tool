from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import REPORTS_DIR
from app import db

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
