# Sitemap & URL Health Checker — Design & Implementation Document

*Reviewed and finalized: August 20, 2026*

## 1. Objective

Build a publicly accessible web application hosted on Render that allows a user to enter one or more sitemap URLs and scan 20,000+ URLs.

The application will:
- Discover URLs from XML sitemaps and sitemap indexes.
- Check every URL.
- Detect HTTP, redirect, accessibility, SEO, and content problems.
- Show live scan progress.
- Generate an Excel report.
- Allow the user to download the report.
- Require no database.
- Require no R2/object storage.
- Use only the application's temporary filesystem.
- Use a single Python/FastAPI application containing the UI and crawler.

## 2. Project Philosophy: Simple, Open, No Gatekeeping

Per direction: **no authentication, no SSRF/domain blocking, no rate limiting, no per-URL or per-scan caps.** Anyone can scan any number of URLs from any domain. This is a personal/internal tool, not a hardened public service — trust is assumed.

The only limits kept are **operational, not security-related** — they exist so a scan actually finishes on limited hardware, not to restrict who can use it:

| Item | Kept? | Why |
|---|---|---|
| SSRF / private-IP blocking | ❌ Removed | Not a security tool — any URL is fetchable, including internal ones if the host can reach them |
| Per-IP / per-session rate limiting | ❌ Removed | Anyone can start any number of scans |
| Max discovered URLs cap | ❌ Removed | No limit on sitemap size |
| Authentication / login | ❌ Removed | Fully open |
| Domain allowlist | ❌ Removed | Any domain is fair game |
| Crawl concurrency (default 25) | ✅ Kept | Purely a performance knob — controls how fast *your own* crawl runs, adjustable in the UI |
| `.xml.gz` decompression | ✅ Kept, uncapped | Simplicity over robustness, per direction |
| openpyxl write-only mode | ✅ Kept | Just an implementation detail to avoid OOM on large reports, not a restriction |
| Single worker process | ✅ Kept | Needed for in-memory scan state to work at all |

**One thing worth knowing, not a recommendation to change anything:** with no cap on discovered URLs, a very large or malformed sitemap (e.g. millions of entries, or a redirect loop in sitemap indexes) could run for a very long time or exhaust memory on Render. If that ever happens in practice, the fix is a soft warning in the UI ("this sitemap has 500K+ URLs, this may take hours") rather than a hard block — easy to add later without touching the core design.

## 3. Architecture

```
Internet
    │
    ▼
┌────────────────────┐
│       Render        │
│                      │
│   Python App         │
│  ┌────────────────┐  │
│  │    FastAPI      │  │
│  └───────┬─────────┘  │
│  ┌───────▼─────────┐  │
│  │ HTML/CSS/JS UI   │  │
│  └───────┬─────────┘  │
│  ┌───────▼─────────┐  │
│  │ Sitemap Engine   │  │
│  └───────┬─────────┘  │
│  ┌───────▼─────────┐  │
│  │ Async Crawler    │  │
│  └───────┬─────────┘  │
│  ┌───────▼─────────┐  │
│  │ HTML Analyzer    │  │
│  └───────┬─────────┘  │
│  ┌───────▼─────────┐  │
│  │ Excel Generator  │  │
│  └───────┬─────────┘  │
│        /reports       │
└──────────┬────────────┘
           ▼
     Excel Download
```

Single deployable application.

## 4. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Server | Uvicorn (`--workers 1`) |
| HTML templating | Jinja2 |
| CSS | Plain CSS |
| JavaScript | Vanilla JS |
| HTTP client | httpx |
| XML parsing | lxml |
| HTML parsing | BeautifulSoup4 / lxml |
| Excel | openpyxl (write-only mode) |
| Compression | gzip (size-capped) |
| Async processing | asyncio |
| Hosting | Render |
| Database | None |
| Object storage | None |
| Queue | None |

Avoid React, Next.js, Redis, PostgreSQL, Celery for v1.

## 5. Application Structure

```
sitemap-checker/
├── app/
│   ├── main.py
│   ├── routes/
│   │   ├── pages.py
│   │   ├── scan.py
│   │   └── reports.py
│   ├── crawler/
│   │   ├── sitemap.py
│   │   ├── crawler.py
│   │   ├── http_checker.py
│   │   ├── html_analyzer.py
│   │   └── robots.py
│   ├── reports/
│   │   └── excel.py
│   ├── models/
│   │   └── scan_models.py
│   ├── config.py
│   └── utils.py
├── templates/
│   ├── index.html
│   ├── scan.html
│   └── report.html
├── static/
│   ├── css/style.css
│   └── js/app.js
├── reports/
├── requirements.txt
├── Dockerfile
├── .gitignore
├── README.md
└── render.yaml
```

## 6. Main UI

Simple single-page form:
- Sitemap URL (required)
- Additional sitemap URLs (optional, textarea)
- Concurrent requests dropdown (default 25)
- Start Scan button

If the supplied URL is a sitemap index, child sitemaps are auto-discovered.

## 7. Sitemap Processing

Support: `<urlset>`, `<sitemapindex>`, `.xml`, `.xml.gz` (size-capped), nested indexes, multiple sitemap URLs, dedup, normalization.

Validate: invalid XML, invalid sitemap, missing `<loc>`, invalid URL, duplicate URL, unsupported protocol.

## 8. URL Normalization

- Configurable trailing-slash handling
- Strip fragments (`#...`)
- Allow: HTTP, HTTPS
- Reject: `javascript:`, `mailto:`, `data:`, `ftp:`
- Dedup after normalization

## 9. Crawler

Async, batched (not all 20K at once):

```
Default concurrency: 25
Maximum concurrency: 50
Connection timeout: 10s
Read timeout: 20s
Redirects: enabled, max 10
Retry: 1
Per-host concurrency: 10
Global concurrency: 25
```

## 10. HTTP Checks

Record per URL: status, final URL, redirect count, response time, content type, content length, error.

Status categories: 2xx success / 3xx redirect / 4xx client error / 5xx server error. Also detect: DNS errors, SSL errors, connection errors, timeout.

## 11. Redirect Analysis

Track full redirect chain length and detect: loops, cross-domain redirects, HTTP→HTTPS, sitemap URL → different canonical.

## 12. HTML Analysis

Extract (size-capped per page, see §2): title, meta description, H1, H2 count, word count, HTML size, text size, canonical tag(s), robots meta (`noindex`/`nofollow`).

## 13. SEO Checks

**Critical:** 4xx, 5xx, timeout, DNS failure, invalid response.

**Warnings:** missing/empty/long/short title, missing/long meta description, missing H1, multiple H1s, missing/multiple canonical, noindex, nofollow, sitemap URL redirects.

**Duplicates** (post-crawl aggregation): duplicate title, description, canonical, H1.

## 14. Content Analysis

```
< 100 words       Very thin
100–299 words     Thin
300+ words        Normal
```
Warnings, not automatic failures — some page types legitimately have little text.

**Soft-404 detection:** HTTP 200 but body contains phrases like "page not found," "content unavailable," or has near-zero meaningful content.

**Application-error detection:** HTTP 200 but body contains "internal server error," "exception," "database error," etc.

## 15. Broken Images (optional, off by default)

Extract `<img src>`, optionally verify each. Off by default because it multiplies request volume significantly on 20K-page crawls.

## 16. Internal Links (optional, off by default)

Same rationale as images — off by default for v1.

## 17. Robots.txt

Fetch and parse before scanning. Report existence, accessibility, declared sitemaps.

**Default behavior:** robots.txt is informational only — disallowed URLs are still fetched and checked like any other URL, just labeled in the report (e.g. "disallowed by robots.txt"). No enforcement, per the open-access direction in §2.

## 18. Sitemap vs Page Comparison

For every sitemap URL, compare against actual HTTP status, canonical target, robots directive, and indexability. Flag mismatches (e.g. sitemap URL ≠ canonical, sitemap URL → 404/noindex/redirect).

## 19. Live Progress UI

Poll `GET /api/scan/{scan_id}/status` every 1–2s. No WebSocket needed for v1. Show totals, status breakdown, average response time, elapsed/estimated time (labeled as estimate).

## 20. Scan Lifecycle

```
START → Validate sitemap → Discover sitemaps → Extract URLs → Deduplicate
  → Start crawler → Update progress → Analyze pages
  → Aggregate duplicate issues → Generate Excel → COMPLETED
```

## 21. Scan States

In-memory dict, single-worker process only (see §2):
```python
scans = { scan_id: scan_state }
```
States: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.

## 22. Cancel Scan

`POST /api/scan/{scan_id}/cancel` — crawler stops gracefully after in-flight requests complete.

## 23. Excel Report

Filename: `sitemap_scan_YYYY-MM-DD_HHMMSS.xlsx`

- **Sheet 1 — Summary**: scan info, result counts, SEO/content issue counts
- **Sheet 2 — All URLs**: full column set (URL, status, final URL, redirect count, response time, content type/size, title, meta description, H1, word count, canonical, robots, indexable, issue)
- **Sheet 3 — Errors**: 4xx/5xx/timeout/DNS/SSL only
- **Sheet 4 — SEO Issues**
- **Sheet 5 — Content Issues**: thin content, soft-404, application errors
- **Sheet 6 — Redirects**: chains
- **Sheet 7 — Duplicates**

Generated once, at scan completion (see §2 re: progressive-generation conflict).

## 24. Excel Formatting

Frozen header row, auto filters, sensible column widths, wrapped text, color coding (green/yellow/red/orange by status), human-readable issue labels (e.g. "❌ 404 Not Found", "⚠ Thin content: 87 words").

## 25. File Management

Store in `/reports/`. Auto-delete files older than 24h (or configurable, e.g. 7 days). Treat Render's filesystem as ephemeral, not permanent.

## 26. Security

None by design (see §2). Any URL, any domain, any scheme the HTTP client supports is fetchable. No IP blocking, no domain restriction, no auth.

## 27. Abuse Protection

None by design (see §2). No caps on sitemap count, URL count, sitemap size, nesting depth, or scan duration. Crawl concurrency remains adjustable purely as a performance setting, not a limit on usage.

## 28. User-Agent

```
SitemapHealthChecker/1.0 (+https://your-domain.example)
```

## 29. Retry Strategy

Retry once (exponential backoff, 1s/2s): timeout, 502, 503, 504.
No retry: 404, 410, 401, 403.

## 30. Rate Limiting

Global concurrency 25, per-host concurrency 10 — prevents hammering any single target domain regardless of sitemap size.

## 31. Scan Options (v1: hide behind defaults)

Concurrency, timeout, follow-redirects, check-SEO, check-content (on by default); check-images, check-internal-links (off by default); custom user agent.

## 32. API Design

```
POST   /api/scan                       → { scan_id, status }
GET    /api/scan/{scan_id}/status      → progress + counts
POST   /api/scan/{scan_id}/cancel
GET    /api/scan/{scan_id}/download
GET    /
```

## 33. Render Deployment Considerations

- Single worker process (state consistency — see §2)
- Bounded concurrency (protects both Render instance and target sites)
- Discard full HTML after per-page analysis — never hold 20K full documents in memory
- Handle shutdown/restart gracefully (in-progress scans should fail cleanly, not corrupt state)
- Report generated once at completion, not incrementally

## 34. Performance Target

No fixed duration promise — depends on target server speed. At concurrency 25, expect tens of minutes for 20K URLs against typical sites. UI shows elapsed time + estimated remaining, labeled as an estimate.

## 35. Error Handling

One failed URL never terminates the scan — record and continue. Sitemap-level failure (can't fetch/parse the sitemap itself) does prevent scan start.

## 36. Logging

```
SCAN_STARTED, SITEMAP_DISCOVERED, URL_CHECK_STARTED, URL_CHECK_FAILED,
SCAN_PROGRESS, SCAN_COMPLETED, REPORT_GENERATED
```
Never log full HTML response bodies.

## 37. Home Page Summary (post-scan)

Total checked, status breakdown (200/3xx/4xx/5xx/other), SEO issue count, content issue count, duration, download + new-scan buttons.

## 38. v1 Feature Set

**Must have:** sitemap URL input, index support, multi-sitemap, extraction, dedup, async crawler, status code categorization, timeout/DNS/SSL detection, redirect detection + final URL + response time, HTML parsing (title/meta/H1/canonical/robots/word count), thin-content + soft-404 + application-error detection, live progress, cancel, Excel export, summary, temporary storage, **plus the guardrails in §2**.

**v1.1:** broken image checking, internal link checking, structured data validation, Open Graph, hreflang, sitemap-vs-robots.txt comparison, page screenshots.

**Avoid initially:** user accounts, database, Redis, persistent storage, AI analysis, login, complex dashboard, React, microservices.

## 39. Final Architecture Diagram

```
┌──────────────────────────────┐
│            Render            │
│       Python 3.12            │
│  ┌────────────────────────┐  │
│  │        FastAPI         │  │
│  └───────────┬────────────┘  │
│  ┌───────────▼────────────┐  │
│  │      HTML / CSS / JS   │  │
│  └───────────┬────────────┘  │
│  ┌───────────▼────────────┐  │
│  │    Scan Controller     │  │
│  └───────────┬────────────┘  │
│       ┌──────▼──────┐        │
│       │   Sitemap   │        │
│       │   Parser    │        │
│       └──────┬──────┘        │
│       ┌──────▼──────┐        │
│       │ Async HTTP  │        │
│       │   Crawler   │        │
│       └──────┬──────┘        │
│       ┌──────▼──────┐        │
│       │ HTML/SEO/   │        │
│       │  Content    │        │
│       │  Analyzer   │        │
│       └──────┬──────┘        │
│       ┌──────▼──────┐        │
│       │   Excel     │        │
│       │  Generator  │        │
│       └─────────────┘        │
└──────────────────────────────┘
```
  ▼
Analyze pages
  │
  ▼
Aggregate duplicate issues
  │
  ▼
Generate Excel
  │
  ▼
COMPLETED


---

21. Scan States

Use simple in-memory state:

QUEUED
RUNNING
COMPLETED
FAILED
CANCELLED

No database is necessary.

For example:

scans = {
    scan_id: scan_state
}

This is sufficient for a single Render instance.


---

22. Cancel Scan

UI:

[ CANCEL SCAN ]

API:

POST /api/scan/{scan_id}/cancel

The crawler should gracefully stop after completing the current requests.


---

23. Excel Report

Generate:

sitemap_scan_2026-08-20_222500.xlsx

Sheet 1 — Summary

Scan Information

Sitemap
Date
Duration
Total URLs

Results

200
3xx
4xx
5xx
Timeout
DNS
SSL

SEO Issues
Content Issues

Sheet 2 — All URLs

Columns:

URL
Status
Final URL
Redirect Count
Response Time
Content Type
Content Size
Title
Title Length
Meta Description
Meta Description Length
H1
H1 Count
Word Count
Canonical
Robots
Indexable
Issue

Sheet 3 — Errors

Only:

4xx
5xx
Timeout
DNS
SSL

Sheet 4 — SEO Issues

Only problematic SEO pages.

Sheet 5 — Content Issues

Only:

Thin content
Very thin content
Possible soft 404
Possible application error

Sheet 6 — Redirects

Original URL
Final URL
Status
Redirect Count
Redirect Chain

Sheet 7 — Duplicates

Issue Type
Value
URL


---

24. Excel Formatting

Use:

Freeze header row

Auto filters

Column widths

Wrapped text

Excel tables

Separate sheets

Summary statistics


Use visual highlighting:

200      → green
3xx      → yellow
4xx      → red
5xx      → red
Warnings → orange

And make the Issue column human-readable:

❌ 404 Not Found

⚠ Missing title

⚠ Thin content: 87 words

❌ 500 Internal Server Error

⚠ Sitemap URL redirects

⚠ Canonical differs from sitemap URL


---

25. File Management

Use:

/reports

Files:

reports/
├── scan_20260820_220001.xlsx
├── scan_20260820_221504.xlsx
└── scan_20260820_223002.xlsx

Automatically delete reports older than:

24 hours

or configurable:

7 days

Because Render's filesystem should be treated as temporary, not permanent storage.


---

26. Security

Because the application accepts arbitrary URLs, security is extremely important.

SSRF protection

Do not allow the crawler to freely access internal infrastructure.

Block:

localhost
127.0.0.1
0.0.0.0
::1
10.0.0.0/8
172.16.0.0/12
192.168.0.0/16
169.254.0.0/16

Also protect against:

file://
ftp://
javascript:
data:

Validate URLs before requesting them.

Domain restriction option

For your personal use, an even safer mode would be:

Allowed domains:
tollybo.com
www.tollybo.com

For a public tool, allow arbitrary public domains but block private/internal addresses.


---

27. Abuse Protection

Since this is publicly hosted, someone could submit enormous sitemaps.

Set limits:

Maximum sitemap URLs: 50
Maximum discovered URLs: 50,000
Maximum sitemap size: 50 MB
Maximum sitemap nesting: 3
Maximum concurrent requests: 50
Maximum scan duration: configurable

For v1:

Maximum URLs = 25,000

You can increase it later.


---

28. User-Agent

Don't use a generic browser UA.

Use something identifiable:

SitemapHealthChecker/1.0

Optionally:

SitemapHealthChecker/1.0 (+https://your-domain.example)

This helps website owners identify your crawler.


---

29. Retry Strategy

Don't retry everything aggressively.

Recommended:

Timeout       → retry once
502           → retry once
503           → retry once
504           → retry once

404           → no retry
410           → no retry
401           → no retry
403           → no retry

Use exponential backoff:

1 second
2 seconds


---

30. Rate Limiting

Default:

25 concurrent requests

But introduce per-host control.

For example, if a sitemap contains:

20,000 URLs from example.com

don't hammer it with 50 simultaneous requests.

Use:

Per-host concurrency = 10
Global concurrency = 25

This is much safer.


---

31. Scan Options

Basic UI:

Scan Options

Concurrency
[ 25 ]

Request timeout
[ 20 seconds ]

☑ Follow redirects
☑ Check SEO
☑ Check content
☐ Check images
☐ Check internal links

User Agent
[ SitemapHealthChecker/1.0 ]

For the first release, hide advanced options and use sensible defaults.


---

32. API Design

Start scan

POST /api/scan

Request:

{
  "sitemaps": [
    "https://example.com/sitemap.xml"
  ]
}

Response:

{
  "scan_id": "abc123",
  "status": "QUEUED"
}

Status

GET /api/scan/{scan_id}/status

Response:

{
  "scan_id": "abc123",
  "status": "RUNNING",
  "total": 20438,
  "completed": 8421,
  "success": 8102,
  "redirects": 201,
  "client_errors": 92,
  "server_errors": 12,
  "timeouts": 14,
  "percentage": 41.12
}

Cancel

POST /api/scan/{scan_id}/cancel

Download

GET /api/scan/{scan_id}/download

Home

GET /


---

33. Important Render Consideration

The biggest risk is the free service sleeping/restarting.

Therefore the crawler should:

Limit concurrency.

Save intermediate results to a temporary file.

Avoid keeping the entire HTML of 20K pages in memory.

Process each URL and discard HTML after analysis.

Generate the final Excel progressively where practical.

Handle shutdown gracefully.


Memory should remain roughly:

URL list
+
current concurrent responses
+
results

not:

20,000 full HTML documents in RAM


---

34. Performance Target

For 20K URLs, don't promise a fixed duration because it depends heavily on target servers.

A reasonable target:

Concurrency: 25

20,000 URLs
       ↓
Fast sites
       ↓
potentially tens of minutes

The UI should therefore always display:

Elapsed time
Estimated remaining time

but label the ETA as an estimate.


---

35. Error Handling

If one URL fails:

URL fails
   ↓
record error
   ↓
continue next URL

Never allow one bad URL to terminate the entire scan.

If sitemap download fails:

Scan cannot start

If 1 page fails:

Scan continues


---

36. Logging

Server logs:

SCAN_STARTED
SITEMAP_DISCOVERED
URL_CHECK_STARTED
URL_CHECK_FAILED
SCAN_PROGRESS
SCAN_COMPLETED
REPORT_GENERATED

Don't log complete HTML responses.

For example:

INFO scan=abc123 completed=5000 total=20438
WARNING scan=abc123 url=... status=500


---

37. Home Page Summary

After completion:

Scan Complete ✓

20,438 URLs checked

        19,812
          321
          182
           23
          100

200 OK
Redirects
4xx
5xx
Other

SEO Issues       438
Content Issues   192

Duration         18m 42s

[ Download Excel ]
[ New Scan ]


---

38. Recommended v1 Feature Set

I would not implement every possible SEO crawler feature immediately.

Must have

[x] Sitemap URL input

[x] Sitemap index support

[x] Multiple sitemaps

[x] URL extraction

[x] Deduplication

[x] Async crawler

[x] 2xx/3xx/4xx/5xx

[x] Timeout detection

[x] DNS/SSL errors

[x] Redirect detection

[x] Final URL

[x] Response time

[x] HTML parsing

[x] Title

[x] Meta description

[x] H1

[x] Canonical

[x] Robots/noindex

[x] Word count

[x] Thin content warning

[x] Soft-404 detection

[x] Application-error detection

[x] Live progress

[x] Cancel

[x] Excel

[x] Summary

[x] Temporary report storage


V1.1

[ ] Broken image checking

[ ] Internal link checking

[ ] Structured data validation

[ ] Open Graph

[ ] hreflang

[ ] Sitemap vs robots.txt comparison

[ ] Page screenshot


Avoid initially

❌ User accounts

❌ Database

❌ Redis

❌ Persistent storage

❌ AI analysis

❌ Login

❌ Complex dashboard

❌ React

❌ Microservices



---

39. Final Architecture

┌──────────────────────────────┐
                    │            Render            │
                    │                              │
                    │       Python 3.12            │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │        FastAPI         │  │
                    │  └───────────┬────────────┘  │
                    │              │               │
                    │  ┌───────────▼────────────┐  │
                    │  │      HTML / CSS / JS   │  │
                    │  └───────────┬────────────┘  │
                    │              │               │
                    │  ┌───────────▼────────────┐  │
                    │  │    Scan Controller     │  │
                    │  └───────────┬────────────┘  │
                    │              │               │
                    │       ┌──────▼──────┐        │
                    │       │   Sitemap   │        │
                    │       │   Parser    │        │
                    │       └──────┬──────┘        │
                    │              │               │
                    │       ┌──────▼──────┐        │
                    │       │ Async HTTP  │        │
                    │       │   Crawler   │        │
                    │       └──────┬──────┘        │
                    │              │               │
                    │       ┌──────▼──────┐        │
                    │       │ HTML/SEO/   │        │
                    │       │  Content    │        │
                    │       │  Analyzer   │        │
                    │       └──────┬──────┘        │
                    │              │               │
                 
