# Sitemap & URL Health Checker

A web application that scans XML sitemaps, checks thousands of URLs for HTTP/SEO/content issues, and generates Excel reports with live progress tracking.

**Live:** [sitemap-analizer-tool.onrender.com](https://sitemap-analizer-tool.onrender.com)

## Features

- **Sitemap Discovery** — Parses `<urlset>`, `<sitemapindex>`, `.xml`, `.xml.gz` (size-capped), nested indexes, multiple sitemap URLs
- **Async Crawler** — Concurrent URL checking with configurable concurrency (10–50), per-host limits, redirect tracking
- **HTTP Analysis** — Status codes, response time, content type/size, redirect chains, DNS/SSL/timeout detection
- **SEO Analysis** — Title, meta description, H1, canonical, robots/noindex, word count
- **Content Analysis** — Thin content detection, soft-404, application errors
- **Live Progress** — Real-time progress bar, stats, current URL, recent results table
- **Excel Reports** — 8-sheet workbook with summary, all URLs, errors, SEO issues, content issues, redirects, duplicates, common issues
- **Scan Detail Page** — Full analysis view with download, URL analytics, and issue breakdown
- **Search Page** — Look up any scan by ID, view recent scans
- **Persistent Storage** — Turso (libSQL) database, scans persist across restarts
- **Partial Reports** — Download results while scan is still running

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI |
| Server | Uvicorn (single worker) |
| Database | Turso (libSQL/SQLite) |
| HTTP Client | httpx |
| XML Parsing | lxml |
| HTML Parsing | BeautifulSoup4 |
| Excel | openpyxl |
| Frontend | Vanilla JS + CSS |

## Project Structure

```
sitemap-analizer-tool/
├── app/
│   ├── main.py              # FastAPI app, lifespan, static mounts
│   ├── config.py            # All settings, env vars
│   ├── db.py                # Turso/SQLite database layer
│   ├── models/
│   │   └── scan_models.py   # ScanStatus enum, URLResult dataclass
│   ├── crawler/
│   │   ├── sitemap.py       # Sitemap parsing, URL extraction
│   │   ├── crawler.py       # Async crawler with batching
│   │   ├── http_checker.py  # HTTP request handling
│   │   ├── html_analyzer.py # BeautifulSoup SEO/content analysis
│   │   └── robots.py        # robots.txt fetcher
│   ├── reports/
│   │   └── excel.py         # 8-sheet Excel report generator
│   └── routes/
│       ├── pages.py         # HTML page routes
│       ├── scan.py          # Scan lifecycle API
│       └── reports.py       # Download, summary, analytics API
├── templates/
│   ├── index.html           # Main form + progress + results
│   ├── search.html          # Search scan by ID
│   ├── scan_detail.html     # Full scan analysis page
│   ├── urls.html            # URL analytics (searchable, paginated)
│   ├── url_detail.html      # Single URL detail view
│   └── issues.html          # Common issues (tabbed)
├── static/
│   ├── css/style.css        # Main styles
│   └── css/pages.css        # Analytics/issues/detail styles
│   └── js/app.js            # Main UI logic
├── requirements.txt
├── Dockerfile
└── render.yaml
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/scan` | Start a new scan |
| `GET` | `/api/scan/{id}/status` | Scan progress + counts |
| `POST` | `/api/scan/{id}/cancel` | Cancel a running scan |
| `GET` | `/api/scan/{id}/download` | Download completed Excel report |
| `GET` | `/api/scan/{id}/download-partial` | Download partial report (while running) |
| `GET` | `/api/scan/{id}/summary` | Error/SEO/content summary |
| `GET` | `/api/scan/{id}/urls` | Paginated URL results (searchable) |
| `GET` | `/api/scan/{id}/url/{result_id}` | Single URL detail |
| `GET` | `/api/scan/{id}/issues` | All issues grouped by type |
| `GET` | `/api/search/recent-scans` | Recent scans list |

## Pages

| Path | Description |
|---|---|
| `/` | Main page — start scan, view progress, download report |
| `/search` | Search for a scan by ID, view recent scans |
| `/scan/{id}` | Full scan detail — summary, issues, SEO, content, errors |
| `/scan/{id}/urls` | URL analytics — searchable, filterable, paginated table |
| `/scan/{id}/url/{id}` | Single URL analysis detail |
| `/scan/{id}/issues` | Common issues — tabbed view (All/SEO/Content/Errors) |

## Configuration

Environment variables (set in Render dashboard):

| Variable | Description | Default |
|---|---|---|
| `TURSO_DATABASE_URL` | Turso database URL | falls back to local SQLite |
| `TURSO_AUTH_TOKEN` | Turso auth token | falls back to local SQLite |

## Crawl Settings

| Setting | Value |
|---|---|
| Default concurrency | 25 |
| Max concurrency | 50 |
| Per-host concurrency | 10 |
| Connect timeout | 10s |
| Read timeout | 20s |
| Max redirects | 10 |
| Retry count | 1 (exponential backoff) |
| Report retention | 7 days |

## Deployment

```bash
# Local development
pip install -r requirements.txt
uvicorn app.main:app --reload

# Render (auto-deployed from GitHub)
# render.yaml handles build + start command
```

## Excel Report Sheets

1. **Summary** — Scan info, result counts, SEO/content issue counts
2. **All URLs** — Full column set: URL, status, final URL, redirects, response time, title, meta, H1, word count, canonical, robots, issues
3. **Errors** — 4xx/5xx/timeout/DNS/SSL only
4. **SEO Issues** — Missing title, meta, H1, canonical, noindex
5. **Content Issues** — Thin content, soft-404, application errors
6. **Redirects** — Original URL, final URL, redirect chain
7. **Common Issues** — All issues sorted by affected page count
8. **Duplicates** — Duplicate titles, descriptions, canonicals, H1s

## License

Private project.
