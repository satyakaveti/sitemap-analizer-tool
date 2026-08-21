import re
from urllib.parse import urlparse, parse_qs

from app.crawler.priority import make_issue
from app.utils import strip_www


def analyze_url(url: str, page_domain: str = "") -> list[dict]:
    issues = []
    parsed = urlparse(url)

    if parsed.scheme == "http" and parsed.netloc:
        issues.append(make_issue("URL_HTTP_NOT_HTTPS", "URL uses HTTP, not HTTPS"))

    if " " in url:
        issues.append(make_issue("URL_SPACES", "URL contains spaces"))

    invalid = re.findall(r'[<>\[\]{}|\\^`]', url)
    if invalid:
        issues.append(make_issue("URL_INVALID_CHARS", f"Contains: {''.join(set(invalid))}"))

    if len(url) > 2048:
        issues.append(make_issue("URL_TOO_LONG", f"{len(url)} chars (max recommended: 2048)"))

    if parsed.path != parsed.path.lower() and parsed.path != "/":
        issues.append(make_issue("URL_UPPERCASE", "Path contains uppercase characters"))

    if "//" in parsed.path:
        issues.append(make_issue("URL_MULTIPLE_SLASH", "Path contains consecutive slashes"))

    params = parse_qs(parsed.query)
    if len(params) > 5:
        issues.append(make_issue("URL_EXCESS_PARAMS", f"{len(params)} query parameters"))

    if "#" in url and parsed.fragment:
        issues.append(make_issue("URL_FRAGMENT_IN_SITEMAP", "URL contains fragment (#)"))

    if page_domain:
        host_domain = strip_www(parsed.netloc.lower())
        if host_domain and host_domain != strip_www(page_domain.lower()):
            issues.append(make_issue("LINK_EXTERNAL_URL", f"External domain: {host_domain}"))

    return issues
