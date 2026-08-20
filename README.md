# sitemap-analizer-tool
sitemap-analizer-tool


Absolutely. For your use case, I’d keep the first version single-app, lightweight, filesystem-based, and focused on sitemap/URL health + SEO/content diagnostics.

Sitemap & URL Health Checker — Design & Implementation Document

1. Objective

Build a publicly accessible web application hosted on Render that allows a user to enter one or more sitemap URLs and scan 20,000+ URLs.

The application will:

Discover URLs from XML sitemaps and sitemap indexes.

Check every URL.

Detect HTTP, redirect, accessibility, SEO, and content problems.

Show live scan progress.

Generate an Excel report.

Allow the user to download the report.

Require no database.

Require no R2/object storage.

Use only the application's temporary filesystem.

Use a single Python/FastAPI application containing the UI and crawler.



---

2. Architecture

Internet
                            │
                            ▼
                  ┌────────────────────┐
                  │       Render       │
                  │                    │
                  │   Python App       │
                  │                    │
                  │ ┌────────────────┐ │
                  │ │    FastAPI     │ │
                  │ └───────┬────────┘ │
                  │         │          │
                  │ ┌───────▼────────┐ │
                  │ │ HTML/CSS/JS UI  │ │
                  │ └───────┬────────┘ │
                  │         │          │
                  │ ┌───────▼────────┐ │
                  │ │ Sitemap Engine  │ │
                  │ └───────┬────────┘ │
                  │         │          │
                  │ ┌───────▼────────┐ │
                  │ │ Async Crawler   │ │
                  │ └───────┬────────┘ │
                  │         │          │
                  │ ┌───────▼────────┐ │
                  │ │ HTML Analyzer   │ │
                  │ └───────┬────────┘ │
                  │         │          │
                  │ ┌───────▼────────┐ │
                  │ │ Excel Generator │ │
                  │ └───────┬────────┘ │
                  │         │          │
                  │      /reports      │
                  └─────────┬──────────┘
                            │
                            ▼
                       Excel Download

There is one deployable application.


---

3. Technology Stack

Component	Technology

Language	Python 3.12+
Web framework	FastAPI
Server	Uvicorn
HTML	Jinja2
CSS	Plain CSS
JavaScript	Vanilla JavaScript
HTTP client	httpx
XML parsing	lxml
HTML parsing	BeautifulSoup4 / lxml
Excel	openpyxl
Compression	gzip support
Async processing	asyncio
Hosting	Render
Database	None
Object storage	None
Queue	None


Avoid React, Next.js, Redis, PostgreSQL, Celery, etc. for v1.


---

4. Application Structure

sitemap-checker/
│
├── app/
│   ├── main.py
│   │
│   ├── routes/
│   │   ├── pages.py
│   │   ├── scan.py
│   │   └── reports.py
│   │
│   ├── crawler/
│   │   ├── sitemap.py
│   │   ├── crawler.py
│   │   ├── http_checker.py
│   │   ├── html_analyzer.py
│   │   └── robots.py
│   │
│   ├── reports/
│   │   └── excel.py
│   │
│   ├── models/
│   │   └── scan_models.py
│   │
│   ├── config.py
│   └── utils.py
│
├── templates/
│   ├── index.html
│   ├── scan.html
│   └── report.html
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
│
├── reports/
│
├── requirements.txt
├── Dockerfile
├── .gitignore
├── README.md
└── render.yaml


---

5. Main UI

The home page should be intentionally simple.

┌────────────────────────────────────────────────────────┐
│                 Sitemap Health Checker                 │
│                                                        │
│ Check 20,000+ URLs for HTTP, SEO and content issues.  │
│                                                        │
│ Sitemap URL                                            │
│ ┌────────────────────────────────────────────────────┐ │
│ │ https://example.com/sitemap-index.xml             │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ Additional Sitemap URLs                               │
│ ┌────────────────────────────────────────────────────┐ │
│ │ https://example.com/sitemap-movies.xml            │ │
│ │ https://example.com/sitemap-reviews.xml           │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ Concurrent requests: [ 25 ▼ ]                         │
│                                                        │
│                  [ START SCAN ]                        │
│                                                        │
└────────────────────────────────────────────────────────┘

For v1, I'd allow either:

One sitemap index URL

Multiple sitemap URLs


If the supplied URL is a sitemap index, automatically discover child sitemaps.


---

6. Sitemap Processing

Support:

Standard sitemap

<urlset>
    <url>
        <loc>https://example.com/page</loc>
    </url>
</urlset>

Sitemap index

<sitemapindex>
    <sitemap>
        <loc>https://example.com/sitemap1.xml</loc>
    </sitemap>
    <sitemap>
        <loc>https://example.com/sitemap2.xml</loc>
    </sitemap>
</sitemapindex>

Support

.xml

.xml.gz

Sitemap indexes

Nested sitemap indexes

Multiple sitemap URLs

Duplicate URLs

URL normalization


Validate

Invalid XML
Invalid sitemap
Missing <loc>
Invalid URL
Duplicate URL
Unsupported protocol


---

7. URL Normalization

Normalize URLs before crawling.

Examples:

https://example.com/page
https://example.com/page/

should be treated according to configuration.

Remove unnecessary fragments:

https://example.com/page#reviews

→

https://example.com/page

Support:

HTTP

HTTPS


Reject:

javascript:

mailto:

data:

ftp:


Optionally detect duplicate URLs after normalization.


---

8. Crawler

Use asynchronous HTTP requests.

Example configuration:

Default concurrency: 25
Maximum concurrency: 50
Connection timeout: 10 seconds
Read timeout: 20 seconds
Redirects: enabled
Maximum redirects: 10
Retry: 1

Do not immediately fire 20,000 requests simultaneously.

Instead:

20,000 URLs

Batch/concurrency pool
       │
       ├── URL 1
       ├── URL 2
       ├── ...
       └── URL 25

       ↓

next URLs

This protects both:

your Render instance

the target website



---

9. HTTP Checks

Every URL should record:

Field	Example

URL	/movies/darling
Status	200
Final URL	/movies/darling
Redirect count	0
Response time	0.42s
Content type	text/html
Content length	84 KB
Error	None


Status categories

Success

200–299

Redirect

300–399

Client error

400–499

Server error

500–599

Specific issues

Detect:

301

302

307

308

404

410

401

403

429

500

502

503

504

DNS errors

SSL errors

Connection errors

Timeout



---

10. Redirect Analysis

For every redirect:

Original URL
     ↓
301
     ↓
URL 2
     ↓
301
     ↓
URL 3

Report:

Redirect chain: 2

Detect:

Redirect

Redirect chain

Redirect loop

Redirect to different domain

HTTP → HTTPS

Sitemap URL → different canonical URL



---

11. HTML Analysis

For successful HTML pages, download and parse the HTML.

Extract:

Basic

Title
Meta description
H1
H2 count
Word count
HTML size
Text size

Canonical

<link rel="canonical" href="...">

Check:

Missing canonical

Multiple canonical tags

Canonical points elsewhere

Canonical is invalid


Robots

Detect:

<meta name="robots" content="noindex">

and:

<meta name="robots" content="nofollow">

Report:

indexable
noindex
nofollow
noindex,nofollow


---

12. SEO Checks

The report should detect:

Critical

HTTP 4xx

HTTP 5xx

Timeout

DNS failure

Invalid response


Warnings

Missing <title>

Empty title

Very long title

Very short title

Missing meta description

Very long meta description

Missing H1

Multiple H1s

Missing canonical

Multiple canonical tags

noindex

nofollow

Sitemap URL redirects


Duplicates

After all URLs are scanned:

Duplicate title

Duplicate description

Duplicate canonical

Duplicate H1


This requires an aggregation stage after crawling.


---

13. Content Analysis

This is particularly important for your use case.

Detect:

Empty content

Very little text

Thin content

Configurable threshold:

< 100 words       Very thin
100–299 words     Thin
300+ words        Normal

But these should be warnings, not automatic failures.

A movie page could legitimately have limited text.

Soft 404 detection

A page returns:

HTTP 200

but contains:

Page not found
Movie not found
404
Content unavailable

or has extremely little meaningful content.

Report:

⚠ Possible soft 404


---

14. Detect Application Error Pages

This is very useful.

For example:

HTTP 200

but HTML contains:

Internal Server Error
Something went wrong
Application Error
Exception
Database error

Report:

❌ Possible application error

This catches situations where your application incorrectly returns 200.


---

15. Broken Images

For each HTML page:

Extract:

<img src="...">

Then optionally check image URLs.

For example:

/movie/darling

Images: 8
Working: 7
Broken: 1

I'd make this optional, because checking 20K pages + every image can multiply the number of requests dramatically.

UI:

☑ Check images
☐ Check external links

Default:

Check images = OFF


---

16. Internal Links

Optional second-level analysis.

For each page:

Internal links: 42
Broken internal links: 2

Again, make it optional for v1 because a 20K-page crawl can become much larger.


---

17. Robots.txt

Before scanning:

https://example.com/robots.txt

Check:

Exists

Accessible

Sitemap declarations

Basic robots directives


Do not automatically treat robots.txt disallow as an HTTP failure.

Report separately:

Robots.txt
──────────────
Accessible: Yes
Sitemaps: 5


---

18. Sitemap vs Page Comparison

This is one of the most useful features.

For every sitemap URL:

Sitemap URL
    ↓
HTTP status
    ↓
Canonical
    ↓
robots
    ↓
indexability

Example:

Sitemap:
https://tollybo.com/movie/darling

HTTP:
200

Canonical:
https://tollybo.com/movies/darling

Result:
⚠ Sitemap URL differs from canonical

Also detect:

Sitemap URL → 404
Sitemap URL → noindex
Sitemap URL → redirect
Sitemap URL → canonical elsewhere


---

19. Live Progress UI

Do not wait until the entire scan completes.

Show:

Scanning...

Total URLs:       20,438
Completed:         8,321
Remaining:        12,117

Progress
████████░░░░░░░░░░ 40.7%

200 OK             8,002
3xx                  152
4xx                  112
5xx                   11
Timeout               44
Other                 0

Average response:   0.83 sec

Update every 1–2 seconds.

For v1, simple polling is enough:

GET /api/scan/{scan_id}/status

No WebSocket required.


---

20. Scan Lifecycle

START
  │
  ▼
Validate sitemap
  │
  ▼
Discover sitemaps
  │
  ▼
Extract URLs
  │
  ▼
Deduplicate
  │
  ▼
Start crawler
  │
  ▼
Update progress
  │
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
                 
