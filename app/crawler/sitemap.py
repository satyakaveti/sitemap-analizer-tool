import gzip
import logging
from io import BytesIO
from typing import Optional
from xml.etree import ElementTree

import httpx
from lxml import etree

from app.config import MAX_XML_GZ_SIZE, USER_AGENT
from app.utils import normalize_url, is_valid_url, resolve_sitemap_url

logger = logging.getLogger(__name__)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


async def fetch_sitemap(url: str, client: httpx.AsyncClient) -> Optional[bytes]:
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        content = resp.content
        if url.endswith(".gz"):
            if len(content) > MAX_XML_GZ_SIZE:
                logger.warning(f"Sitemap too large: {url} ({len(content)} bytes)")
                return None
            content = gzip.decompress(content)
        return content
    except Exception as e:
        logger.error(f"Failed to fetch sitemap {url}: {e}")
        return None


def parse_xml(raw: bytes) -> Optional[etree._Element]:
    try:
        return etree.HTML(raw) if raw[:5] == b"<html" else etree.fromstring(raw)
    except Exception:
        try:
            return etree.parse(BytesIO(raw)).getroot()
        except Exception as e:
            logger.error(f"Failed to parse XML: {e}")
            return None


def parse_urlset(root: etree._Element) -> list[str]:
    urls = []
    for loc in root.iter(f"{{{SITEMAP_NS}}}loc"):
        if loc.text:
            urls.append(loc.text.strip())
    if not urls:
        for loc in root.iter("loc"):
            if loc.text:
                urls.append(loc.text.strip())
    return urls


def parse_sitemap_index(root: etree._Element) -> list[str]:
    sitemaps = []
    for loc in root.iter(f"{{{SITEMAP_NS}}}loc"):
        if loc.text:
            sitemaps.append(loc.text.strip())
    if not sitemaps:
        for loc in root.iter("loc"):
            if loc.text:
                sitemaps.append(loc.text.strip())
    return sitemaps


def is_sitemap_index(root: etree._Element) -> bool:
    if root.tag == f"{{{SITEMAP_NS}}}sitemapindex":
        return True
    if root.tag == "sitemapindex":
        return True
    for child in root:
        if "sitemap" in child.tag.lower():
            return True
    return False


async def extract_all_urls(
    sitemap_urls: list[str], state, max_depth: int = 5
) -> list[str]:
    all_urls: set[str] = set()
    visited_sitemaps: set[str] = set()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:

        async def _process(url: str, depth: int = 0):
            if depth > max_depth or url in visited_sitemaps:
                return
            if state.is_cancelled:
                return
            visited_sitemaps.add(url)

            raw = await fetch_sitemap(url, client)
            if raw is None:
                return

            root = parse_xml(raw)
            if root is None:
                return

            if is_sitemap_index(root):
                child_urls = parse_sitemap_index(root)
                for child in child_urls:
                    child_resolved = resolve_sitemap_url(url, child)
                    await _process(child_resolved, depth + 1)
            else:
                found = parse_urlset(root)
                for u in found:
                    normalized = normalize_url(u)
                    if normalized and is_valid_url(normalized):
                        all_urls.add(normalized)

        for surl in sitemap_urls:
            await _process(surl)

    return list(all_urls)
