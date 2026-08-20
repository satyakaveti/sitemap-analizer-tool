import logging
import asyncio

import httpx
from bs4 import BeautifulSoup

from app.config import (
    CONNECT_TIMEOUT, READ_TIMEOUT, MAX_REDIRECTS,
    USER_AGENT, MAX_HTML_PARSE_SIZE,
    THIN_CONTENT_THRESHOLD, VERY_THIN_CONTENT_THRESHOLD,
    LONG_TITLE_THRESHOLD, SHORT_TITLE_THRESHOLD, LONG_META_DESC_THRESHOLD,
)
from app.models.scan_models import URLResult

logger = logging.getLogger(__name__)

SOFT_404_PHRASES = [
    "page not found", "content unavailable", "does not exist",
    "no longer available", "been removed", "broken link",
    "404 error", "not found", "doesn't exist",
]

APP_ERROR_PHRASES = [
    "internal server error", "exception", "database error",
    "stack trace", "traceback", "application error",
    "500 error", "server error",
]


def analyze_html(html_content: bytes, url: str) -> dict:
    result = {}
    try:
        text = html_content[:MAX_HTML_PARSE_SIZE].decode("utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")

        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else ""
        result["title_length"] = len(result["title"])

        meta_desc = soup.find("meta", attrs={"name": "description"})
        result["meta_description"] = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else ""
        result["meta_description_length"] = len(result["meta_description"])

        h1_tags = soup.find_all("h1")
        result["h1"] = h1_tags[0].get_text(strip=True) if h1_tags else ""
        result["h1_count"] = len(h1_tags)

        body = soup.find("body")
        result["word_count"] = len(body.get_text().split()) if body else 0

        canonical = soup.find("link", attrs={"rel": "canonical"})
        result["canonical"] = canonical["href"].strip() if canonical and canonical.get("href") else ""

        robots_meta = soup.find("meta", attrs={"name": "robots"})
        result["robots"] = robots_meta["content"].strip() if robots_meta and robots_meta.get("content") else ""

        result["indexable"] = True
        robots_content = result["robots"].lower()
        if "noindex" in robots_content:
            result["indexable"] = False

        issues = _check_seo_issues(result)
        issues += _check_content_issues(result, text)
        result["issues"] = issues

    except Exception as e:
        result["issues"] = [f"Parse error: {e}"]
        result["title"] = ""
        result["meta_description"] = ""
        result["h1"] = ""
        result["canonical"] = ""
        result["robots"] = ""
        result["indexable"] = True
        result["word_count"] = 0

    return result


def _check_seo_issues(data: dict) -> list[str]:
    issues = []
    if not data.get("title"):
        issues.append("Missing title")
    elif data["title_length"] > LONG_TITLE_THRESHOLD:
        issues.append(f"Title too long: {data['title_length']} chars")
    elif data["title_length"] < SHORT_TITLE_THRESHOLD:
        issues.append(f"Title too short: {data['title_length']} chars")

    if not data.get("meta_description"):
        issues.append("Missing meta description")
    elif data["meta_description_length"] > LONG_META_DESC_THRESHOLD:
        issues.append(f"Meta description too long: {data['meta_description_length']} chars")

    if data.get("h1_count", 0) == 0:
        issues.append("Missing H1")
    elif data.get("h1_count", 0) > 1:
        issues.append(f"Multiple H1 tags: {data['h1_count']}")

    if not data.get("canonical"):
        issues.append("Missing canonical tag")

    if "noindex" in data.get("robots", "").lower():
        issues.append("Page has noindex directive")
    if "nofollow" in data.get("robots", "").lower():
        issues.append("Page has nofollow directive")

    return issues


def _check_content_issues(data: dict, html_text: str) -> list[str]:
    issues = []
    wc = data.get("word_count", 0)

    if wc < VERY_THIN_CONTENT_THRESHOLD:
        issues.append(f"Very thin content: {wc} words")
    elif wc < THIN_CONTENT_THRESHOLD:
        issues.append(f"Thin content: {wc} words")

    lower_text = html_text.lower()
    for phrase in SOFT_404_PHRASES:
        if phrase in lower_text:
            issues.append("Possible soft 404")
            break

    for phrase in APP_ERROR_PHRASES:
        if phrase in lower_text:
            issues.append("Possible application error")
            break

    return issues
