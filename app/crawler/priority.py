"""
Issue priority and severity classification.

Severity levels: error, warning, info
Priority levels: critical, high, medium, low, info
"""

from dataclasses import dataclass


@dataclass
class IssueCode:
    code: str
    severity: str  # error | warning | info
    priority: str  # critical | high | medium | low | info


ISSUE_CODES: dict[str, IssueCode] = {
    # --- HTTP Response ---
    "HTTP_4XX":               IssueCode("HTTP_4XX", "error", "high"),
    "HTTP_5XX":               IssueCode("HTTP_5XX", "error", "critical"),
    "HTTP_TIMEOUT":           IssueCode("HTTP_TIMEOUT", "error", "critical"),
    "HTTP_DNS_FAILURE":       IssueCode("HTTP_DNS_FAILURE", "error", "critical"),
    "HTTP_SSL_FAILURE":       IssueCode("HTTP_SSL_FAILURE", "error", "critical"),
    "HTTP_REDIRECT":          IssueCode("HTTP_REDIRECT", "warning", "medium"),
    "HTTP_REDIRECT_CHAIN":    IssueCode("HTTP_REDIRECT_CHAIN", "warning", "medium"),
    "HTTP_REDIRECT_LOOP":     IssueCode("HTTP_REDIRECT_LOOP", "error", "critical"),
    "HTTP_SLOW":              IssueCode("HTTP_SLOW", "warning", "medium"),
    "HTTP_VERY_SLOW":         IssueCode("HTTP_VERY_SLOW", "error", "medium"),
    "HTTP_NON_HTML":          IssueCode("HTTP_NON_HTML", "warning", "medium"),
    "HTTP_TO_HTTPS":          IssueCode("HTTP_TO_HTTPS", "info", "info"),

    # --- Title ---
    "TITLE_MISSING":          IssueCode("TITLE_MISSING", "error", "high"),
    "TITLE_EMPTY":            IssueCode("TITLE_EMPTY", "error", "high"),
    "TITLE_SHORT":            IssueCode("TITLE_SHORT", "warning", "medium"),
    "TITLE_LONG":             IssueCode("TITLE_LONG", "warning", "medium"),
    "TITLE_VERY_LONG":        IssueCode("TITLE_VERY_LONG", "warning", "medium"),
    "TITLE_DUPLICATE":        IssueCode("TITLE_DUPLICATE", "warning", "medium"),

    # --- Meta Description ---
    "META_DESC_MISSING":      IssueCode("META_DESC_MISSING", "warning", "medium"),
    "META_DESC_EMPTY":        IssueCode("META_DESC_EMPTY", "warning", "medium"),
    "META_DESC_SHORT":        IssueCode("META_DESC_SHORT", "warning", "medium"),
    "META_DESC_LONG":         IssueCode("META_DESC_LONG", "warning", "medium"),
    "META_DESC_VERY_LONG":    IssueCode("META_DESC_VERY_LONG", "warning", "medium"),
    "META_DESC_DUPLICATE":    IssueCode("META_DESC_DUPLICATE", "warning", "medium"),

    # --- H1 ---
    "H1_MISSING":             IssueCode("H1_MISSING", "error", "high"),
    "H1_EMPTY":               IssueCode("H1_EMPTY", "error", "high"),
    "H1_MULTIPLE":            IssueCode("H1_MULTIPLE", "warning", "medium"),

    # --- Canonical ---
    "CANONICAL_MISSING":      IssueCode("CANONICAL_MISSING", "warning", "medium"),
    "CANONICAL_MULTIPLE":     IssueCode("CANONICAL_MULTIPLE", "error", "high"),
    "CANONICAL_INVALID":      IssueCode("CANONICAL_INVALID", "error", "high"),
    "CANONICAL_CROSS_DOMAIN": IssueCode("CANONICAL_CROSS_DOMAIN", "warning", "medium"),
    "CANONICAL_NOINDEX":      IssueCode("CANONICAL_NOINDEX", "error", "critical"),
    "CANONICAL_4XX":          IssueCode("CANONICAL_4XX", "error", "high"),
    "CANONICAL_5XX":          IssueCode("CANONICAL_5XX", "error", "critical"),
    "CANONICAL_REDIRECT":     IssueCode("CANONICAL_REDIRECT", "warning", "medium"),

    # --- Robots / Indexability ---
    "ROBOTS_NOINDEX":         IssueCode("ROBOTS_NOINDEX", "warning", "medium"),
    "ROBOTS_NOFOLLOW":        IssueCode("ROBOTS_NOFOLLOW", "warning", "low"),
    "ROBOTS_NONE":            IssueCode("ROBOTS_NONE", "warning", "medium"),
    "ROBOTS_TXT_BLOCKED":     IssueCode("ROBOTS_TXT_BLOCKED", "error", "critical"),
    "SITEMAP_NOINDEX":        IssueCode("SITEMAP_NOINDEX", "error", "critical"),
    "SITEMAP_ROBOTS_BLOCKED": IssueCode("SITEMAP_ROBOTS_BLOCKED", "error", "critical"),

    # --- Soft 404 ---
    "SOFT_404_POSSIBLE":      IssueCode("SOFT_404_POSSIBLE", "warning", "medium"),
    "SOFT_404_LIKELY":        IssueCode("SOFT_404_LIKELY", "warning", "high"),
    "SOFT_404_STRONG":        IssueCode("SOFT_404_STRONG", "error", "critical"),

    # --- Content ---
    "CONTENT_THIN":           IssueCode("CONTENT_THIN", "warning", "medium"),
    "CONTENT_VERY_THIN":      IssueCode("CONTENT_VERY_THIN", "warning", "medium"),
    "CONTENT_WRONG_TYPE":     IssueCode("CONTENT_WRONG_TYPE", "warning", "medium"),
    "CONTENT_DUPLICATE":      IssueCode("CONTENT_DUPLICATE", "warning", "medium"),
    "CONTENT_NEAR_DUPLICATE": IssueCode("CONTENT_NEAR_DUPLICATE", "warning", "medium"),
    "APP_ERROR_PAGE":         IssueCode("APP_ERROR_PAGE", "error", "high"),

    # --- URL Structure ---
    "URL_HTTP_NOT_HTTPS":     IssueCode("URL_HTTP_NOT_HTTPS", "warning", "medium"),
    "URL_SPACES":             IssueCode("URL_SPACES", "warning", "low"),
    "URL_INVALID_CHARS":      IssueCode("URL_INVALID_CHARS", "error", "high"),
    "URL_TOO_LONG":           IssueCode("URL_TOO_LONG", "warning", "low"),
    "URL_UPPERCASE":          IssueCode("URL_UPPERCASE", "info", "info"),
    "URL_MULTIPLE_SLASH":     IssueCode("URL_MULTIPLE_SLASH", "warning", "low"),
    "URL_EXCESS_PARAMS":      IssueCode("URL_EXCESS_PARAMS", "warning", "low"),
    "URL_FRAGMENT_IN_SITEMAP": IssueCode("URL_FRAGMENT_IN_SITEMAP", "warning", "low"),
    "URL_4XX":                IssueCode("URL_4XX", "error", "high"),
    "URL_5XX":                IssueCode("URL_5XX", "error", "critical"),

    # --- Internal Links ---
    "LINK_INTERNAL_BROKEN":   IssueCode("LINK_INTERNAL_BROKEN", "error", "high"),
    "LINK_INTERNAL_REDIRECT": IssueCode("LINK_INTERNAL_REDIRECT", "warning", "medium"),
    "LINK_INTERNAL_NOINDEX":  IssueCode("LINK_INTERNAL_NOINDEX", "warning", "medium"),
    "LINK_NO_INTERNAL":       IssueCode("LINK_NO_INTERNAL", "info", "info"),

    # --- External Links ---
    "LINK_EXTERNAL_BROKEN":   IssueCode("LINK_EXTERNAL_BROKEN", "warning", "medium"),
    "LINK_EXTERNAL_REDIRECT": IssueCode("LINK_EXTERNAL_REDIRECT", "info", "info"),
    "LINK_EXTERNAL_URL":      IssueCode("LINK_EXTERNAL_URL", "info", "info"),

    # --- Images ---
    "IMG_ALT_MISSING":        IssueCode("IMG_ALT_MISSING", "warning", "low"),
    "IMG_ALT_EMPTY":          IssueCode("IMG_ALT_EMPTY", "warning", "low"),
    "IMG_DIMENSIONS_MISSING": IssueCode("IMG_DIMENSIONS_MISSING", "warning", "low"),
    "IMG_BROKEN":             IssueCode("IMG_BROKEN", "error", "high"),

    # --- Mobile ---
    "VIEWPORT_MISSING":       IssueCode("VIEWPORT_MISSING", "warning", "low"),

    # --- Structured Data ---
    "SD_INVALID_JSONLD":      IssueCode("SD_INVALID_JSONLD", "warning", "medium"),
    "SD_MISSING_PROPERTY":    IssueCode("SD_MISSING_PROPERTY", "warning", "medium"),
    "SD_INVALID_VALUE":       IssueCode("SD_INVALID_VALUE", "warning", "medium"),

    # --- Open Graph ---
    "OG_MISSING":             IssueCode("OG_MISSING", "warning", "low"),
    "OG_PARTIAL":             IssueCode("OG_PARTIAL", "warning", "low"),
    "OG_INVALID_IMAGE":       IssueCode("OG_INVALID_IMAGE", "warning", "low"),
}


def get_issue(code: str) -> IssueCode:
    if code in ISSUE_CODES:
        return ISSUE_CODES[code]
    return IssueCode(code, "info", "info")


def make_issue(code: str, message: str = "") -> dict:
    ic = get_issue(code)
    return {
        "code": ic.code,
        "severity": ic.severity,
        "priority": ic.priority,
        "message": message or ic.code.replace("_", " ").title(),
    }


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def sort_issues(issues: list[dict]) -> list[dict]:
    return sorted(issues, key=lambda x: PRIORITY_ORDER.get(x.get("priority", "info"), 4))


def has_critical(issues: list[dict]) -> bool:
    return any(i.get("priority") == "critical" for i in issues)


def has_high(issues: list[dict]) -> bool:
    return any(i.get("priority") in ("critical", "high") for i in issues)
