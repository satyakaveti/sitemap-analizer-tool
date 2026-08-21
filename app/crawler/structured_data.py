import json
import logging
import re
from bs4 import BeautifulSoup

from app.crawler.priority import make_issue

logger = logging.getLogger(__name__)

SCHEMA_ORG_TYPES = {
    "Article", "NewsArticle", "BlogPosting", "WebPage", "WebSite",
    "Organization", "Person", "LocalBusiness", "Product", "Review",
    "Offer", "Event", "FAQPage", "HowTo", "BreadcrumbList",
    "ItemList", "VideoObject", "Dataset", "JobPosting",
}

REQUIRED_PROPERTIES = {
    "Article": ["headline", "datePublished"],
    "Product": ["name", "offers"],
    "LocalBusiness": ["name", "address"],
    "JobPosting": ["title", "datePosted", "hiringOrganization"],
    "Event": ["name", "startDate", "location"],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "VideoObject": ["name", "description", "thumbnailUrl", "uploadDate"],
    "Organization": ["name"],
    "Person": ["name"],
    "WebPage": ["name"],
    "WebSite": ["name"],
    "Review": ["itemReviewed"],
}


def analyze_structured_data(html_content: bytes) -> list[dict]:
    issues = []
    try:
        text = html_content.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")

        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        if not scripts:
            return issues

        for script in scripts:
            raw = script.string or ""
            if not raw.strip():
                issues.append(make_issue("SD_INVALID_JSONLD", "Empty JSON-LD block"))
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                issues.append(make_issue("SD_INVALID_JSONLD", f"Invalid JSON: {e}"))
                continue

            items = _as_list(data)
            for item in items:
                issues.extend(_validate_item(item))

    except Exception as e:
        logger.debug(f"Structured data analysis failed: {e}")

    return issues


def _as_list(data) -> list[dict]:
    if isinstance(data, list):
        return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        return [data]
    return []
