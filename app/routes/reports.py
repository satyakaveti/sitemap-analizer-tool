from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import REPORTS_DIR

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
