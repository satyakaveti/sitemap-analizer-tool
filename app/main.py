import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import REPORTS_DIR, REPORT_RETENTION_HOURS
from app.routes import pages, scan, reports
from app import db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.cleanup_old_scans(REPORT_RETENTION_HOURS)
    cleanup_old_reports()
    logger.info("Database initialized, old scans cleaned")
    yield


def cleanup_old_reports():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=REPORT_RETENTION_HOURS)
    for f in REPORTS_DIR.glob("*.xlsx"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink(missing_ok=True)


app = FastAPI(title="Sitemap Health Checker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages.router)
app.include_router(scan.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
