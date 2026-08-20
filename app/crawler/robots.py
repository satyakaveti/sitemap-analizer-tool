import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from lxml import etree

from app.config import USER_AGENT

logger = logging.getLogger(__name__)


@dataclass
class RobotsInfo:
    exists: bool = False
    accessible: bool = False
    sitemaps: list[str] = field(default_factory=list)
    disallowed_paths: list[str] = field(default_factory=list)
    content: str = ""


async def fetch_robots(base_url: str) -> RobotsInfo:
    from urllib.parse import urlparse
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
                info.content = resp.text
                _parse_robots(info)
            elif resp.status_code == 404:
                info.exists = False
                info.accessible = True
            else:
                info.exists = True
                info.accessible = False
    except Exception as e:
        logger.error(f"Failed to fetch robots.txt for {base_url}: {e}")

    return info


def _parse_robots(info: RobotsInfo):
    current_agent = None
    for line in info.content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("user-agent:"):
            current_agent = line.split(":", 1)[1].strip()
        elif line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                info.sitemaps.append(sitemap_url)
        elif line.lower().startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                info.disallowed_paths.append(path)
