from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/scan/{scan_id}/urls")
async def urls_page(request: Request, scan_id: str):
    return templates.TemplateResponse(request, "urls.html", {"scan_id": scan_id})


@router.get("/scan/{scan_id}/url/{result_id}")
async def url_detail_page(request: Request, scan_id: str, result_id: int):
    return templates.TemplateResponse(request, "url_detail.html", {"scan_id": scan_id, "result_id": result_id})


@router.get("/scan/{scan_id}/issues")
async def issues_page(request: Request, scan_id: str):
    return templates.TemplateResponse(request, "issues.html", {"scan_id": scan_id})
