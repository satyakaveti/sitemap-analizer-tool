from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.config import REPORTS_DIR
from app.models.scan_models import ScanState

GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
YELLOW_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
ORANGE_FILL = PatternFill(start_color="FCD5B4", end_color="FCD5B4", fill_type="solid")
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def _style_header(ws, col_count):
    for col in range(1, col_count + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
        cell.border = THIN_BORDER


def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)[:50]))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)


def _status_fill(code):
    if code is None:
        return None
    if 200 <= code < 300:
        return GREEN_FILL
    if 300 <= code < 400:
        return YELLOW_FILL
    if 400 <= code < 500:
        return RED_FILL
    if code >= 500:
        return RED_FILL
    return None


def _write_row(ws, row_num, values, fill=None):
    for col, val in enumerate(values, 1):
        cell = ws.cell(row=row_num, column=col, value=val)
        cell.border = THIN_BORDER
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if fill:
            cell.fill = fill


def generate_report(state: ScanState) -> str:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    filename = f"sitemap_scan_{timestamp}_{state.scan_id}.xlsx"
    filepath = REPORTS_DIR / filename

    wb = Workbook()

    _write_summary(wb, state)
    _write_all_urls(wb, state)
    _write_errors(wb, state)
    _write_seo_issues(wb, state)
    _write_content_issues(wb, state)
    _write_redirects(wb, state)
    _write_duplicates(wb, state)

    wb.save(str(filepath))
    return str(filepath)


def _write_summary(wb, state: ScanState):
    ws = wb.active
    ws.title = "Summary"
    headers = ["Metric", "Value"]
    ws.append(headers)
    _style_header(ws, len(headers))

    rows = [
        ("Sitemaps", ", ".join(state.sitemaps)),
        ("Date", state.started_at.isoformat() if state.started_at else ""),
        ("Duration (seconds)", round(state.elapsed_seconds, 1)),
        ("Total URLs", state.total_urls),
        ("", ""),
        ("200 OK", state.success),
        ("Redirects", state.redirects),
        ("4xx Client Errors", state.client_errors),
        ("5xx Server Errors", state.server_errors),
        ("Timeouts", state.timeouts),
        ("DNS Errors", state.dns_errors),
        ("SSL Errors", state.ssl_errors),
        ("Other Errors", state.other_errors),
        ("", ""),
        ("SEO Issues", state.seo_issues),
        ("Content Issues", state.content_issues),
    ]
    for row in rows:
        ws.append(row)

    _auto_width(ws)


def _write_all_urls(wb, state: ScanState):
    ws = wb.create_sheet("All URLs")
    headers = [
        "URL", "Status", "Final URL", "Redirect Count", "Response Time",
        "Content Type", "Content Size", "Title", "Title Length",
        "Meta Description", "Meta Desc Length", "H1", "H1 Count",
        "Word Count", "Canonical", "Robots", "Indexable", "Issues",
    ]
    ws.append(headers)
    _style_header(ws, len(headers))

    for r in state.results:
        row = [
            r.url, r.status_code, r.final_url, r.redirect_count,
            r.response_time, r.content_type, r.content_length,
            r.title, r.title_length, r.meta_description,
            r.meta_description_length, r.h1, r.h1_count,
            r.word_count, r.canonical, r.robots,
            "Yes" if r.indexable else "No",
            "; ".join(r.issues) if r.issues else "",
        ]
        fill = _status_fill(r.status_code)
        _write_row(ws, ws.max_row + 1, row, fill)

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    _auto_width(ws)


def _write_errors(wb, state: ScanState):
    ws = wb.create_sheet("Errors")
    headers = ["URL", "Status", "Error", "Response Time"]
    ws.append(headers)
    _style_header(ws, len(headers))

    for r in state.results:
        if r.status_code and (r.status_code >= 400) or r.error:
            _write_row(ws, ws.max_row + 1, [
                r.url, r.status_code or "N/A", r.error or "", r.response_time
            ], RED_FILL)

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    _auto_width(ws)


def _write_seo_issues(wb, state: ScanState):
    ws = wb.create_sheet("SEO Issues")
    headers = ["URL", "Status", "Issue"]
    ws.append(headers)
    _style_header(ws, len(headers))

    seo_keywords = ["title", "meta", "h1", "canonical", "noindex", "nofollow"]
    for r in state.results:
        seo_issues = [i for i in r.issues if any(k in i.lower() for k in seo_keywords)]
        if seo_issues:
            _write_row(ws, ws.max_row + 1, [
                r.url, r.status_code or "N/A", "; ".join(seo_issues)
            ], ORANGE_FILL)

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    _auto_width(ws)


def _write_content_issues(wb, state: ScanState):
    ws = wb.create_sheet("Content Issues")
    headers = ["URL", "Status", "Word Count", "Issue"]
    ws.append(headers)
    _style_header(ws, len(headers))

    content_keywords = ["thin", "soft", "word", "error"]
    for r in state.results:
        content_issues = [i for i in r.issues if any(k in i.lower() for k in content_keywords)]
        if content_issues:
            _write_row(ws, ws.max_row + 1, [
                r.url, r.status_code or "N/A", r.word_count, "; ".join(content_issues)
            ], ORANGE_FILL)

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    _auto_width(ws)


def _write_redirects(wb, state: ScanState):
    ws = wb.create_sheet("Redirects")
    headers = ["Original URL", "Final URL", "Status", "Redirect Count", "Chain"]
    ws.append(headers)
    _style_header(ws, len(headers))

    for r in state.results:
        if r.redirect_count > 0:
            chain = " -> ".join(r.redirect_chain + [r.final_url or r.url])
            _write_row(ws, ws.max_row + 1, [
                r.url, r.final_url, r.status_code, r.redirect_count, chain
            ], YELLOW_FILL)

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    _auto_width(ws)


def _write_duplicates(wb, state: ScanState):
    ws = wb.create_sheet("Duplicates")
    headers = ["Issue Type", "Value", "URL"]
    ws.append(headers)
    _style_header(ws, len(headers))

    title_map: dict[str, list[str]] = {}
    desc_map: dict[str, list[str]] = {}
    canonical_map: dict[str, list[str]] = {}
    h1_map: dict[str, list[str]] = {}

    for r in state.results:
        if r.title:
            title_map.setdefault(r.title, []).append(r.url)
        if r.meta_description:
            desc_map.setdefault(r.meta_description, []).append(r.url)
        if r.canonical:
            canonical_map.setdefault(r.canonical, []).append(r.url)
        if r.h1:
            h1_map.setdefault(r.h1, []).append(r.url)

    for label, mapping in [("Duplicate Title", title_map), ("Duplicate Description", desc_map),
                           ("Duplicate Canonical", canonical_map), ("Duplicate H1", h1_map)]:
        for value, urls in mapping.items():
            if len(urls) > 1:
                for url in urls:
                    _write_row(ws, ws.max_row + 1, [label, value[:100], url])

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    _auto_width(ws)
