import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config import (
    MAX_HTML_PARSE_SIZE,
    THIN_CONTENT_THRESHOLD, VERY_THIN_CONTENT_THRESHOLD,
)
from app.crawler.priority import make_issue
from app.utils import get_domain, strip_www

logger = logging.getLogger(__name__)

SOFT_404_PHRASES = [
    "page not found", "content unavailable", "does not exist",
    "no longer available", "been removed", "broken link",
    "404 error", "doesn't exist",
]

APP_ERROR_PHRASES = [
    "internal server error", "exception", "database error",
    "stack trace", "traceback", "application error",
    "500 error", "server error",
]


def analyze_html(html_content: bytes, url: str, page_domain: str = "", short_scan: bool = False) -> dict:
    result = {
        "title": "", "title_length": 0,
        "meta_description": "", "meta_description_length": 0,
        "h1": "", "h1_count": 0,
        "word_count": 0,
        "canonical": "", "robots": "", "indexable": True,
        "viewport": "", "og_tags": {},
        "links": [], "images": [],
        "internal_link_count": 0, "external_link_count": 0,
        "image_count": 0, "image_no_alt_count": 0,
        "issues": [],
    }
    try:
        text = html_content[:MAX_HTML_PARSE_SIZE].decode("utf-8", errors="ignore")

        if short_scan:
            # Bypass BeautifulSoup entirely using fast regex and string splitting
            title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""
            result["title"] = title
            result["title_length"] = len(title)
            
            # Simple text length and fast word count estimation
            # Remove inline tags content to estimate meaningful words
            clean_text = re.sub(r"<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>", "", text, flags=re.IGNORECASE | re.DOTALL)
            clean_text = re.sub(r"<[^>]+>", " ", clean_text)
            words = clean_text.split()
            result["word_count"] = len(words)
            
            wc = result["word_count"]
            if wc > 0 and wc < VERY_THIN_CONTENT_THRESHOLD:
                result["issues"].append(make_issue("CONTENT_VERY_THIN", f"Only {wc} meaningful words"))
            elif wc >= VERY_THIN_CONTENT_THRESHOLD and wc < THIN_CONTENT_THRESHOLD:
                result["issues"].append(make_issue("CONTENT_THIN", f"{wc} meaningful words"))
            return result

        soup = BeautifulSoup(text, "html.parser")

        result.update(_analyze_title(soup))
        result.update(_analyze_meta_description(soup))
        result.update(_analyze_h1(soup))
        result.update(_analyze_canonical(soup, url))
        result.update(_analyze_robots(soup))
        result.update(_analyze_viewport(soup))
        result.update(_analyze_og(soup))
        result["word_count"] = _count_meaningful_words(soup)

        links = _extract_links(soup, url, page_domain)
        images = _extract_images(soup)

        result["links"] = links
        result["internal_link_count"] = sum(1 for l in links if l.get("is_internal", True))
        result["external_link_count"] = sum(1 for l in links if not l.get("is_internal", True))
        result["images"] = images
        result["image_count"] = len(images)
        result["image_no_alt_count"] = sum(1 for img in images if not img.get("alt", "").strip())

        result["issues"] = (
            _check_title(result)
            + _check_meta_description(result)
            + _check_h1(result)
            + _check_canonical(result, url)
            + _check_robots(result)
            + _check_content(result, text)
            + _check_viewport(result)
            + _check_og(result)
        )

    except Exception as e:
        logger.debug(f"HTML parse failed for {url}: {e}")
        result["issues"] = [make_issue("APP_ERROR_PAGE", f"Parse error: {e}")]

    return result


def _extract_links(soup: BeautifulSoup, page_url: str, page_domain: str) -> list[dict]:
    links = []
    page_domain = page_domain or get_domain(page_url)

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        try:
            from urllib.parse import urljoin
            full_url = urljoin(page_url, href)
            parsed = urlparse(full_url)
            link_domain = strip_www(parsed.netloc.lower())
            is_internal = link_domain == strip_www(page_domain.lower()) if page_domain else True

            links.append({
                "href": full_url,
                "text": tag.get_text(strip=True)[:100],
                "is_internal": is_internal,
                "rel": tag.get("rel", []),
            })
        except Exception:
            continue

    return links


def _extract_images(soup: BeautifulSoup) -> list[dict]:
    images = []
    for tag in soup.find_all("img"):
        src = tag.get("src", "")
        alt = tag.get("alt")
        width = tag.get("width", "")
        height = tag.get("height", "")
        loading = tag.get("loading", "")

        if src:
            images.append({
                "src": src[:500],
                "alt": alt if alt is not None else "",
                "width": str(width),
                "height": str(height),
                "loading": loading,
            })

    return images


def _analyze_title(soup: BeautifulSoup) -> dict:
    tag = soup.find("title")
    title = tag.get_text(strip=True) if tag else ""
    return {"title": title, "title_length": len(title)}


def _analyze_meta_description(soup: BeautifulSoup) -> dict:
    tag = soup.find("meta", attrs={"name": "description"})
    desc = tag["content"].strip() if tag and tag.get("content") else ""
    return {"meta_description": desc, "meta_description_length": len(desc)}


def _analyze_h1(soup: BeautifulSoup) -> dict:
    h1_tags = soup.find_all("h1")
    h1_text = h1_tags[0].get_text(strip=True) if h1_tags else ""
    return {"h1": h1_text, "h1_count": len(h1_tags)}


def _analyze_canonical(soup: BeautifulSoup, url: str) -> dict:
    canonicals = soup.find_all("link", attrs={"rel": "canonical"})
    count = len(canonicals)
    if count == 1:
        href = canonicals[0].get("href", "").strip()
        return {"canonical": href, "_raw_canonical_count": count}
    elif count > 1:
        href = canonicals[0].get("href", "").strip()
        return {"canonical": href, "_raw_canonical_count": count}
    return {"canonical": "", "_raw_canonical_count": 0}


def _analyze_robots(soup: BeautifulSoup) -> dict:
    tag = soup.find("meta", attrs={"name": "robots"})
    content = tag["content"].strip() if tag and tag.get("content") else ""
    indexable = "noindex" not in content.lower()
    return {"robots": content, "indexable": indexable}


def _analyze_viewport(soup: BeautifulSoup) -> dict:
    tag = soup.find("meta", attrs={"name": "viewport"})
    content = tag["content"].strip() if tag and tag.get("content") else ""
    return {"viewport": content}


def _analyze_og(soup: BeautifulSoup) -> dict:
    og = {}
    for prop in ["title", "description", "image", "url", "type"]:
        tag = soup.find("meta", attrs={"property": f"og:{prop}"})
        if tag and tag.get("content"):
            og[prop] = tag["content"].strip()
    return {"og_tags": og}


def _count_meaningful_words(soup: BeautifulSoup) -> int:
    body = soup.find("body")
    if not body:
        return 0
    for tag in body.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
        tag.decompose()
    text = body.get_text(separator=" ", strip=True)
    return len(text.split())


def _check_title(data: dict) -> list[dict]:
    issues = []
    title = data["title"]
    length = data["title_length"]

    if not title:
        issues.append(make_issue("TITLE_MISSING"))
    elif length < 20:
        issues.append(make_issue("TITLE_SHORT", f"Title is {length} chars (recommended: 20–60)"))
    elif length <= 60:
        pass
    elif length <= 70:
        issues.append(make_issue("TITLE_LONG", f"Title is {length} chars (recommended: 20–60)"))
    else:
        issues.append(make_issue("TITLE_VERY_LONG", f"Title is {length} chars (recommended: 20–60)"))

    return issues


def _check_meta_description(data: dict) -> list[dict]:
    issues = []
    desc = data["meta_description"]
    length = data["meta_description_length"]

    if not desc:
        issues.append(make_issue("META_DESC_MISSING"))
    elif length < 70:
        issues.append(make_issue("META_DESC_SHORT", f"Description is {length} chars (recommended: 70–160)"))
    elif length <= 160:
        pass
    elif length <= 180:
        issues.append(make_issue("META_DESC_LONG", f"Description is {length} chars (recommended: 70–160)"))
    else:
        issues.append(make_issue("META_DESC_VERY_LONG", f"Description is {length} chars (recommended: 70–160)"))

    return issues


def _check_h1(data: dict) -> list[dict]:
    issues = []
    count = data["h1_count"]
    h1 = data["h1"]

    if count == 0:
        issues.append(make_issue("H1_MISSING"))
    elif count > 1:
        issues.append(make_issue("H1_MULTIPLE", f"Found {count} H1 tags"))
    elif not h1:
        issues.append(make_issue("H1_EMPTY"))

    return issues


def _check_canonical(data: dict, url: str) -> list[dict]:
    issues = []
    canonical = data.get("canonical", "")

    if not canonical:
        issues.append(make_issue("CANONICAL_MISSING"))
    else:
        try:
            parsed = urlparse(canonical)
            if not parsed.scheme and not parsed.netloc:
                issues.append(make_issue("CANONICAL_INVALID", f"Invalid canonical: {canonical}"))
            else:
                page_domain = strip_www(urlparse(url).netloc.lower())
                canon_domain = strip_www(parsed.netloc.lower())
                if page_domain and canon_domain and page_domain != canon_domain:
                    issues.append(make_issue("CANONICAL_CROSS_DOMAIN", f"Canonical points to {canon_domain}"))
        except Exception:
            issues.append(make_issue("CANONICAL_INVALID", f"Invalid canonical: {canonical}"))

    canonicals = data.get("_raw_canonical_count", 0)
    if canonicals and canonicals > 1:
        issues.append(make_issue("CANONICAL_MULTIPLE", f"Found {canonicals} canonical tags"))

    return issues


def _check_robots(data: dict) -> list[dict]:
    issues = []
    robots = data.get("robots", "").lower()

    if "noindex" in robots:
        issues.append(make_issue("ROBOTS_NOINDEX"))
    if "nofollow" in robots:
        issues.append(make_issue("ROBOTS_NOFOLLOW"))
    if robots.strip() == "none":
        issues.append(make_issue("ROBOTS_NONE"))

    return issues


def _check_content(data: dict, html_text: str) -> list[dict]:
    issues = []
    wc = data.get("word_count", 0)

    if wc > 0 and wc < VERY_THIN_CONTENT_THRESHOLD:
        issues.append(make_issue("CONTENT_VERY_THIN", f"Only {wc} meaningful words"))
    elif wc >= VERY_THIN_CONTENT_THRESHOLD and wc < THIN_CONTENT_THRESHOLD:
        issues.append(make_issue("CONTENT_THIN", f"{wc} meaningful words"))

    lower_text = html_text.lower()

    soft_404_score = _compute_soft_404_score(data, lower_text)
    if soft_404_score >= 70:
        issues.append(make_issue("SOFT_404_STRONG", f"Soft-404 score: {soft_404_score}"))
    elif soft_404_score >= 50:
        issues.append(make_issue("SOFT_404_LIKELY", f"Soft-404 score: {soft_404_score}"))
    elif soft_404_score >= 30:
        issues.append(make_issue("SOFT_404_POSSIBLE", f"Soft-404 score: {soft_404_score}"))

    for phrase in APP_ERROR_PHRASES:
        if phrase in lower_text:
            issues.append(make_issue("APP_ERROR_PAGE", f"Contains '{phrase}'"))
            break

    return issues


def _compute_soft_404_score(data: dict, lower_text: str) -> int:
    score = 0

    title = data.get("title", "").lower()
    h1 = data.get("h1", "").lower()

    if "404" in title:
        score += 30
    elif "not found" in title:
        score += 30

    if "404" in h1:
        score += 30
    elif "not found" in h1:
        score += 30

    strong_404_phrases = ["page not found", "does not exist", "no longer available", "broken link"]
    for phrase in strong_404_phrases:
        if phrase in lower_text:
            score += 20
            break

    wc = data.get("word_count", 0)
    if wc < 30:
        score += 15

    robots = data.get("robots", "").lower()
    if "noindex" in robots and score > 0:
        score += 10

    return min(score, 100)


def _check_viewport(data: dict) -> list[dict]:
    issues = []
    vp = data.get("viewport", "")
    if not vp:
        issues.append(make_issue("VIEWPORT_MISSING"))
    elif "width=device-width" not in vp:
        issues.append(make_issue("VIEWPORT_MISSING", "Viewport missing width=device-width"))
    return issues


def _check_og(data: dict) -> list[dict]:
    issues = []
    og = data.get("og_tags", {})
    required = ["title", "description", "image", "url", "type"]
    present = [k for k in required if k in og]

    if len(present) == 0:
        issues.append(make_issue("OG_MISSING"))
    elif len(present) < len(required):
        missing = [k for k in required if k not in og]
        issues.append(make_issue("OG_PARTIAL", f"Missing: {', '.join(missing)}"))

    return issues
