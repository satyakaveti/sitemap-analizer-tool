import re
from urllib.parse import urlparse, urldefrag, urljoin
from app.config import ALLOWED_SCHEMES, REJECTED_SCHEMES


def normalize_url(url: str, strip_trailing_slash: bool = True) -> str:
    url = url.strip()
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme.lower() in REJECTED_SCHEMES:
        return ""
    if parsed.scheme and parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    if strip_trailing_slash and normalized.endswith("/") and parsed.path != "/":
        normalized = normalized.rstrip("/")
    return normalized.lower() if not parsed.path else normalized


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ALLOWED_SCHEMES, result.netloc])
    except Exception:
        return False


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def resolve_sitemap_url(base_url: str, relative: str) -> str:
    return urljoin(base_url, relative)
