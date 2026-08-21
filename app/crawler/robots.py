import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from typing import Optional

import httpx

from app.config import USER_AGENT
from app.crawler.priority import make_issue

logger = logging.getLogger(__name__)

ROBOTS_CACHE_TTL = 3600  # 1 hour

_robots_cache: dict[str, dict] = {}


@dataclass
class RobotsRule:
    user_agent: str
    disallow: list[str] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)


@dataclass
class RobotsInfo:
    exists: bool = False
    accessible: bool = False
    sitemaps: list[str] = field(default_factory=list)
    rules: list[RobotsRule] = field(default_factory=list)
    raw_content: str = ""


def _get_cache_key(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_robots_cache(url: str) -> Optional[RobotsInfo]:
    key = _get_cache_key(url)
    cached = _robots_cache.get(key)
    if cached and time.time() - cached["ts"] < ROBOTS_CACHE_TTL:
        return cached["info"]
    return None


def set_robots_cache(url: str, info: RobotsInfo):
    key = _get_cache_key(url)
    _robots_cache[key] = {"info": info, "ts": time.time()}


async def fetch_robots(base_url: str) -> RobotsInfo:
    cached = get_robots_cache(base_url)
    if cached:
        return cached

    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    info = RobotsInfo()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(robots_url)
            if resp.status_code == 200:
                info.exists = True
                info.accessible = True
                info.raw_content = resp.text
                _parse_robots(info)
            elif resp.status_code == 404:
                info.exists = False
                info.accessible = True
            else:
                info.exists = True
                info.accessible = False
    except Exception as e:
        logger.debug(f"Failed to fetch robots.txt for {base_url}: {e}")

    set_robots_cache(base_url, info)
    return info


def _parse_robots(info: RobotsInfo):
    current_rule: Optional[RobotsRule] = None
    agent_rules: dict[str, RobotsRule] = {}

    for line in info.raw_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "user-agent":
            agent = value.lower()
            if agent not in agent_rules:
                agent_rules[agent] = RobotsRule(user_agent=agent)
            current_rule = agent_rules[agent]
        elif key == "disallow" and current_rule:
            if value:
                current_rule.disallow.append(value)
        elif key == "allow" and current_rule:
            if value:
                current_rule.allow.append(value)
        elif key == "sitemap":
            if value:
                info.sitemaps.append(value)

    info.rules = list(agent_rules.values())


def evaluate_robots(url: str, info: RobotsInfo, our_agent: str = USER_AGENT) -> list[dict]:
    issues = []
    if not info.exists or not info.accessible:
        return issues

    parsed = urlparse(url)
    path = parsed.path or "/"

    matched_rules = _find_matching_rules(info.rules, our_agent)

    if matched_rules is None:
        return issues

    for rule in matched_rules:
        for allow_path in rule.allow:
            if _path_matches(path, allow_path):
                return issues

        for disallow_path in rule.disallow:
            if _path_matches(path, disallow_path):
                issues.append(make_issue(
                    "ROBOTS_TXT_BLOCKED",
                    f"Blocked by robots.txt: {disallow_path}"
                ))
                return issues

    return issues


def _find_matching_rules(rules: list[RobotsRule], agent: str) -> Optional[list[RobotsRule]]:
    matched = []
    for rule in rules:
        if rule.user_agent == "*":
            matched.append(rule)
        elif rule.user_agent in agent.lower():
            matched.append(rule)

    if matched:
        return matched

    for rule in rules:
        if rule.user_agent == "*":
            return [rule]

    return None


def _path_matches(path: str, pattern: str) -> bool:
    if not pattern:
        return False

    pattern = pattern.rstrip("*")
    path = path.rstrip("/")

    if not pattern:
        return True

    return path.startswith(pattern)
