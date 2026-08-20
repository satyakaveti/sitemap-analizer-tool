import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import REPORTS_DIR, REPORT_RETENTION_HOURS
from app.routes import pages, scan, reports


def cleanup_old_reports():
    cutoff = datetime.utcnow() - timedelta(hours=REPORT_RETENTION_HOURS)
    for f in REPORTS_DIR.glob("*.xlsx"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink(missing_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_old_reports()
    yield


app = FastAPI(title="Sitemap Health Checker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(pages.router)
app.include_router(scan.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
