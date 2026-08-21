"""
URL Score Engine — 100-point scoring system.

Start at 100, deduct points per issue code.
Score is capped at 0–100.
Rating maps to: Excellent (90–100), Good (75–89), Needs improvement (60–74), Poor (40–59), Critical (0–39).
"""

DEDUCTIONS: dict[str, int] = {
    "HTTP_4XX": 30,
    "HTTP_5XX": 40,
    "HTTP_TIMEOUT": 30,
    "HTTP_DNS_FAILURE": 40,
    "HTTP_SSL_FAILURE": 40,
    "HTTP_REDIRECT": 3,
    "HTTP_REDIRECT_CHAIN": 5,
    "HTTP_SLOW": 5,
    "HTTP_VERY_SLOW": 10,
    "SITEMAP_NOINDEX": 25,
    "SITEMAP_ROBOTS_BLOCKED": 25,
    "SOFT_404_STRONG": 25,
    "SOFT_404_LIKELY": 10,
    "TITLE_MISSING": 15,
    "TITLE_SHORT": 3,
    "TITLE_LONG": 3,
    "TITLE_VERY_LONG": 3,
    "H1_MISSING": 10,
    "H1_EMPTY": 10,
    "H1_MULTIPLE": 3,
    "CANONICAL_MISSING": 8,
    "CANONICAL_CROSS_DOMAIN": 3,
    "CANONICAL_INVALID": 8,
    "CANONICAL_MULTIPLE": 5,
    "CANONICAL_4XX": 15,
    "CANONICAL_5XX": 20,
    "META_DESC_MISSING": 5,
    "META_DESC_SHORT": 2,
    "META_DESC_LONG": 3,
    "META_DESC_VERY_LONG": 3,
    "ROBOTS_NOINDEX": 15,
    "ROBOTS_NOFOLLOW": 5,
    "ROBOTS_TXT_BLOCKED": 10,
    "CONTENT_THIN": 8,
    "CONTENT_VERY_THIN": 12,
    "APP_ERROR_PAGE": 15,
    "LINK_EXTERNAL_BROKEN": 2,
    "IMG_ALT_EMPTY": 2,
    "IMG_DIMENSIONS_MISSING": 1,
    "VIEWPORT_MISSING": 2,
    "OG_MISSING": 1,
    "OG_PARTIAL": 1,
    "SD_INVALID_JSONLD": 2,
    "SD_MISSING_PROPERTY": 2,
    "SD_INVALID_VALUE": 2,
    "URL_HTTP_NOT_HTTPS": 5,
    "URL_SPACES": 3,
    "URL_INVALID_CHARS": 3,
    "URL_TOO_LONG": 2,
    "URL_MULTIPLE_SLASH": 1,
    "URL_EXCESS_PARAMS": 1,
    "URL_4XX": 15,
    "URL_5XX": 20,
}


def compute_score(issues: list[dict]) -> int:
    total_deduction = 0
    for issue in issues:
        code = issue.get("code", "")
        deduction = DEDUCTIONS.get(code, 0)
        total_deduction += deduction

    score = max(0, min(100, 100 - total_deduction))
    return score


def score_rating(score: int) -> str:
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 60:
        return "Needs improvement"
    elif score >= 40:
        return "Poor"
    else:
        return "Critical"
