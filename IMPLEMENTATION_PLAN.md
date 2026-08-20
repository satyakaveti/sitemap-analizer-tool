# Implementation Plan — Sitemap & URL Health Checker

*Created: August 20, 2026*

---

## Overview

This document breaks the project into **9 phases** with discrete tasks. Each phase builds on the previous one. Estimated total: **~40-50 hours** of focused work.

---

## Phase 1: Project Scaffolding

**Goal:** Working skeleton that starts and serves a page.

| # | Task | Details |
|---|------|---------|
| 1.1 | Create directory structure | Exact layout from README §5 |
| 1.2 | `requirements.txt` | fastapi, uvicorn[standard], httpx, lxml, beautifulsoup4, openpyxl, jinja2, python-multipart, aiofiles |
| 1.3 | `app/config.py` | All constants: concurrency defaults (25), timeouts (10s connect, 20s read), max redirects (10), retry config, user agent string, report dir, file retention (24h) |
| 1.4 | `app/main.py` | FastAPI app init, mount static files, include routers, startup/shutdown hooks (report cleanup) |
| 1.5 | `templates/index.html` | Bare-bones form: sitemap URL input, additional sitemaps textarea, concurrency dropdown, start button |
| 1.6 | `static/css/style.css` | Basic styling |
| 1.7 | `static/js/app.js` | Empty skeleton |
| 1.8 | `Dockerfile` | Python 3.12 slim, pip install, uvicorn launch |
| 1.9 | `render.yaml` | Render service definition |
| 1.10 | `.gitignore` | Python, reports/, __pycache__, .env |
| 1.11 | Verify app starts | `uvicorn app.main:app` serves index page |

---

## Phase 2: Data Models & Scan State

**Goal:** Define all data structures before any logic.

| # | Task | Details |
|---|------|---------|
| 2.1 | `app/models/scan_models.py` | `ScanRequest` (pydantic: list of sitemap URLs, options) |
| 2.2 | | `ScanState` dataclass: scan_id, status, total_urls, completed, success, redirects, client_errors, server_errors, timeouts, dns_errors, ssl_errors, started_at, elapsed_seconds, results list |
| 2.3 | | `URLResult` dataclass: url, status_code, final_url, redirect_count, response_time, content_type, content_length, title, title_length, meta_desc, meta_desc_length, h1, h1_count, word_count, canonical, robots, indexable, issues list, is_disallowed, redirect_chain |
| 2.4 | | `ScanStatus` enum: QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED |
| 2.5 | In-memory scan store | `scans: dict[str, ScanState]` in a module-level variable |
| 2.6 | `app/utils.py` | URL normalization (trailing slash, strip fragments, validate scheme) |

---

## Phase 3: Sitemap Parser

**Goal:** Feed it a URL, get back a deduplicated list of page URLs.

| # | Task | Details |
|---|------|---------|
| 3.1 | `app/crawler/sitemap.py` | `fetch_sitemap(url) -> bytes` — fetch with httpx, handle `.xml.gz` decompression (size-capped) |
| 3.2 | | `parse_sitemap(xml_bytes) -> list[str]` — detect `<urlset>` vs `<sitemapindex>` |
| 3.3 | | `parse_urlset(xml) -> list[str]` — extract all `<loc>` values |
| 3.4 | | `parse_sitemap_index(xml) -> list[str]` — extract child sitemap URLs |
| 3.5 | | `extract_all_urls(sitemap_urls) -> list[str]` — recursive index resolution, dedup, normalize, validate |
| 3.6 | | Error handling: invalid XML, missing `<loc>`, bad URLs, unsupported protocols, redirect loops in indexes |
| 3.7 | Unit tests | Test with sample XML fixtures (urlset, index, mixed, malformed, gzipped) |

---

## Phase 4: Async HTTP Crawler

**Goal:** Crawl all URLs concurrently with per-host limiting.

| # | Task | Details |
|---|------|---------|
| 4.1 | `app/crawler/http_checker.py` | `HTTPChecker` class wrapping httpx.AsyncClient |
| 4.2 | | `check_url(url) -> URLResult` — single URL fetch with status, timing, redirects, error capture |
| 4.3 | | Retry logic: timeout/502/503/504 → retry once (1s, 2s backoff); 404/410/401/403 → no retry |
| 4.4 | | Per-host semaphore (`asyncio.Semaphore(10)`) |
| 4.5 | `app/crawler/crawler.py` | `AsyncCrawler` class: orchestrates full scan |
| 4.6 | | `run(urls, options)` — batch URLs, global semaphore (25), update ScanState progress |
| 4.7 | | Cancel support: check `is_cancelled` flag between batches |
| 4.8 | | Callback for progress updates to ScanState |
| 4.9 | Integration tests | Test against a mock HTTP server (httpbin or aiohttp test server) |

---

## Phase 5: HTML & SEO Analysis

**Goal:** Parse each page's HTML and flag issues.

| # | Task | Details |
|---|------|---------|
| 5.1 | `app/crawler/html_analyzer.py` | `analyze_html(html_bytes, url) -> dict` — extract title, meta desc, H1, H2 count, canonical, robots/noindex/nofollow, word count |
| 5.2 | | Content size cap: discard HTML body after analysis, never hold full doc |
| 5.3 | | `detect_soft_404(html_text) -> bool` — check for "page not found", "content unavailable", near-zero content |
| 5.4 | | `detect_app_error(html_text) -> bool` — check for "internal server error", "exception", "database error" |
| 5.5 | | Content thickness: <100 words = "Very thin", 100-299 = "Thin", 300+ = "Normal" |
| 5.6 | | Issue generation: build human-readable issue strings ("⚠ Thin content: 87 words") |
| 5.7 | | SEO issue checks: missing/empty/long title (>60)/short title(<10), missing/long desc(>160), missing H1, multiple H1, missing/multiple canonical, noindex, nofollow |
| 5.8 | | Redirect analysis: cross-domain redirect, HTTP→HTTPS, sitemap URL ≠ final URL |
| 5.9 | | Integrate into crawler flow: fetch → analyze → discard HTML → store result |
| 5.10 | Unit tests | Test with HTML fixture files (good page, thin page, soft 404, app error, no title, multiple H1s, etc.) |

---

## Phase 6: Duplicate Detection & Aggregation

**Goal:** Post-crawl analysis of patterns across all results.

| # | Task | Details |
|---|------|---------|
| 6.1 | Add to `crawler.py` or new `analyzer.py` | After all URLs checked, aggregate: |
| 6.2 | | Duplicate titles (multiple URLs sharing same title) |
| 6.3 | | Duplicate meta descriptions |
| 6.4 | | Duplicate canonical tags |
| 6.5 | | Duplicate H1 tags |
| 6.6 | | Sitemap vs page comparison: sitemap URL → redirect, → 404, → noindex, canonical differs |
| 6.7 | | Append duplicate issues to each affected URLResult |

---

## Phase 7: Excel Report Generator

**Goal:** Generate a formatted, multi-sheet Excel report.

| # | Task | Details |
|---|------|---------|
| 7.1 | `app/reports/excel.py` | `generate_report(scan_state) -> str` (returns file path) |
| 7.2 | | Filename: `sitemap_scan_YYYY-MM-DD_HHMMSS.xlsx` |
| 7.3 | | Sheet 1 — Summary: scan info, counts by status, SEO/content issue counts |
| 7.4 | | Sheet 2 — All URLs: 18 columns (URL, Status, Final URL, Redirect Count, Response Time, Content Type, Content Size, Title, Title Length, Meta Desc, Meta Desc Length, H1, H1 Count, Word Count, Canonical, Robots, Indexable, Issue) |
| 7.5 | | Sheet 3 — Errors: 4xx/5xx/timeout/DNS/SSL only |
| 7.6 | | Sheet 4 — SEO Issues: pages with SEO problems |
| 7.7 | | Sheet 5 — Content Issues: thin/soft-404/app-error |
| 7.8 | | Sheet 6 — Redirects: original URL, final URL, status, count, chain |
| 7.9 | | Sheet 7 — Duplicates: issue type, value, URL |
| 7.10 | | Formatting: frozen header rows, auto-filters, column widths, wrapped text, color coding (green=200, yellow=3xx, red=4xx/5xx, orange=warnings) |
| 7.11 | | Write-only mode for memory safety |
| 7.12 | | Report cleanup: delete files >24h on startup |
| 7.13 | Unit tests | Generate report from mock ScanState, verify sheets exist with correct data |

---

## Phase 8: API Routes & UI

**Goal:** Wire everything together with working endpoints and live progress.

| # | Task | Details |
|---|------|---------|
| 8.1 | `app/routes/pages.py` | `GET /` — serve index.html |
| 8.2 | `app/routes/scan.py` | `POST /api/scan` — validate input, create ScanState, launch background task, return scan_id |
| 8.3 | | `GET /api/scan/{scan_id}/status` — return progress JSON (total, completed, percentages, ETA) |
| 8.4 | | `POST /api/scan/{scan_id}/cancel` — set cancelled flag |
| 8.5 | `app/routes/reports.py` | `GET /api/scan/{scan_id}/download` — serve Excel file |
| 8.6 | | File cleanup endpoint or startup hook |
| 8.7 | `static/js/app.js` | Form submission → POST /api/scan → poll status every 2s → update progress bar → show results → download button |
| 8.8 | | Cancel button wiring |
| 8.9 | `templates/index.html` | Full UI: form, progress section (bar, stats, ETA), results summary section |
| 8.10 | | `templates/scan.html` (if separate) or single-page JS transitions |
| 8.11 | | Status breakdown display: 200/3xx/4xx/5xx/other counts |
| 8.12 | | SEO & content issue counts, duration display |
| 8.13 | | Download Excel + New Scan buttons |

---

## Phase 9: Robots.txt & Polish

**Goal:** Informational robots.txt support and final hardening.

| # | Task | Details |
|---|------|---------|
| 9.1 | `app/crawler/robots.py` | `fetch_robots(domain) -> RobotsInfo` — fetch and parse robots.txt |
| 9.2 | | Store result: exists, accessible, declared sitemaps |
| 9.3 | | Label disallowed URLs in results (informational only, still fetch them) |
| 9.4 | | Integrate into crawl flow: fetch robots.txt before scanning |
| 9.5 | Logging | Add structured logging (SCAN_STARTED, URL_CHECK_FAILED, etc.) — never log HTML bodies |
| 9.6 | Error edge cases | Graceful shutdown handling (in-progress scans fail cleanly) |
| 9.7 | Memory discipline | Verify full HTML is discarded after analysis throughout |
| 9.8 | End-to-end test | Full scan against a real small sitemap (e.g., your own site) |
| 9.9 | Render deployment | Test on Render, verify worker=1, report generation, file cleanup |

---

## Dependency Installation Order

```
Phase 1: pip install fastapi uvicorn[standard] jinja2 python-multipart aiofiles
Phase 3: pip install httpx lxml
Phase 4: (httpx already installed)
Phase 5: pip install beautifulsoup4
Phase 7: pip install openpyxl
```

**Full `requirements.txt`:**
```
fastapi>=0.115
uvicorn[standard]>=0.34
httpx>=0.28
lxml>=5.3
beautifulsoup4>=4.13
openpyxl>=3.1
Jinja2>=3.1
python-multipart>=0.0.18
aiofiles>=24.1
```

---

## File Creation Order

```
1.  requirements.txt
2.  .gitignore
3.  app/__init__.py
4.  app/config.py
5.  app/models/__init__.py
6.  app/models/scan_models.py
7.  app/utils.py
8.  app/main.py
9.  app/routes/__init__.py
10. app/routes/pages.py
11. app/routes/scan.py
12. app/routes/reports.py
13. app/crawler/__init__.py
14. app/crawler/sitemap.py
15. app/crawler/http_checker.py
16. app/crawler/crawler.py
17. app/crawler/html_analyzer.py
18. app/crawler/robots.py
19. app/reports/__init__.py
20. app/reports/excel.py
21. templates/index.html
22. static/css/style.css
23. static/js/app.js
24. Dockerfile
25. render.yaml
```

---

## Key Implementation Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scan state storage | Module-level `dict` | Single worker, no DB needed |
| Background tasks | `asyncio.create_task` | Simple, no Celery/Redis |
| Progress polling | HTTP every 2s | No WebSocket complexity |
| HTML parsing | BeautifulSoup4 on top of lxml | BS4 for ease, lxml for speed |
| Report generation | At completion only | Simpler than progressive; avoids conflict |
| Robots.txt enforcement | Informational only | Per README §2 open-access philosophy |
| Per-host concurrency | `asyncio.Semaphore` per host | Prevents hammering single domains |
| Error per URL | Record and continue | Never kill scan for one bad URL |

---

## Estimated Timeline

| Phase | Hours | Dependency |
|-------|-------|------------|
| 1: Scaffolding | 2-3 | None |
| 2: Data Models | 1-2 | Phase 1 |
| 3: Sitemap Parser | 4-5 | Phase 2 |
| 4: HTTP Crawler | 5-6 | Phase 2 |
| 5: HTML/SEO Analysis | 5-6 | Phase 4 |
| 6: Duplicate Detection | 2-3 | Phase 5 |
| 7: Excel Reports | 4-5 | Phase 6 |
| 8: API Routes & UI | 6-8 | Phases 3-7 |
| 9: Robots.txt & Polish | 3-4 | Phase 8 |
| **Total** | **~35-42** | |

---

## Verification Checklist

- [ ] App starts with `uvicorn app.main:app --workers 1`
- [ ] Index page loads with form
- [ ] Submitting a sitemap URL starts a scan
- [ ] Live progress updates every 2s
- [ ] Cancel button stops scan gracefully
- [ ] Excel downloads with all 7 sheets
- [ ] Color coding works in Excel
- [ ] Large sitemap (1000+ URLs) completes without OOM
- [ ] Report files auto-cleaned after 24h
- [ ] Per-host concurrency caps at 10
- [ ] Global concurrency caps at 25
- [ ] Failed URLs recorded, scan continues
- [ ] Soft-404 pages detected
- [ ] Thin content flagged
- [ ] SEO issues listed (missing title, noindex, etc.)
- [ ] Docker builds and runs
- [ ] Render deployment works
