import gzip
import logging
from io import BytesIO
from typing import Optional

import httpx
from lxml import etree

from app.config import MAX_XML_GZ_SIZE, USER_AGENT
from app.utils import normalize_url, is_valid_url, resolve_sitemap_url

logger = logging.getLogger(__name__)

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _is_html_content(raw: bytes) -> bool:
    snippet = raw[:500].lower().strip()
    return any(tag in snippet for tag in [b"<html", b"<!doc", b"<!doctype", b"<head", b"<body"])


def _fix_xml_entities(raw: bytes) -> bytes:
    text = raw.decode("utf-8", errors="replace")
    fixed = text.replace("&", "&amp;")
    fixed = fixed.replace("&amp;amp;", "&amp;")
    return fixed.encode("utf-8")


async def fetch_sitemap(url: str, client: httpx.AsyncClient) -> Optional[tuple[bytes, str]]:
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        content = resp.content

        if url.endswith(".gz") or "gzip" in content_type or "x-gzip" in content_type:
            if len(content) > MAX_XML_GZ_SIZE:
                logger.warning(f"Sitemap too large: {url} ({len(content)} bytes)")
                return None
            try:
                content = gzip.decompress(content)
            except Exception:
                pass

        if _is_html_content(content):
            logger.warning(f"Sitemap URL returned HTML, not XML: {url}")
            return None

        return (content, content_type)
    except Exception as e:
        logger.error(f"Failed to fetch sitemap {url}: {e}")
        return None


def parse_xml(raw: bytes) -> Optional[etree._Element]:
    try:
        parser = etree.XMLParser(recover=True, resolve_entities=True)
        root = etree.fromstring(raw, parser=parser)
        return root
    except etree.XMLSyntaxError:
        pass

    try:
        fixed = _fix_xml_entities(raw)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(fixed, parser=parser)
        return root
    except Exception:
        pass

    try:
        parser = etree.HTMLParser()
        doc = etree.HTML(raw, parser=parser)
        return doc
    except Exception as e:
        logger.error(f"Failed to parse XML/HTML: {e}")
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
    local_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if local_tag == "sitemapindex":
        return True
    for child in root:
        child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if child_local == "sitemap":
            return True
    return False



def _is_sitemap_url(url: str) -> bool:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    return path.endswith(".xml") or path.endswith(".xml.gz")


async def extract_all_urls(
    scan_id: str, sitemap_urls: list[str], max_depth: int = 5
) -> list[str]:
    from app import db
    import asyncio

    all_urls: set[str] = set()
    visited_sitemaps: set[str] = set()
    cancelled = False

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:

        async def _process(url: str, depth: int = 0):
            nonlocal cancelled
            if cancelled or depth > max_depth or url in visited_sitemaps:
                return
            
            s = db.get_status(scan_id)
            if s and s["is_cancelled"]:
                cancelled = True
                return

            visited_sitemaps.add(url)
            logger.info(f"[scan={scan_id}] Processing sitemap: {url} (depth={depth})")
            
            # Update database status so the user sees progress and current sitemap in the UI
            db.update_scan(
                scan_id, 
                phase=f"Fetching sitemaps ({len(all_urls)} URLs found)", 
                current_url=url[:200]
            )

            if not _is_sitemap_url(url):
                normalized = normalize_url(url)
                if normalized and is_valid_url(normalized):
                    all_urls.add(normalized)
                    logger.info(f"[scan={scan_id}] Added page URL ({len(all_urls)} total): {normalized[:100]}")
                    db.update_scan(
                        scan_id, 
                        phase=f"Fetching sitemaps ({len(all_urls)} URLs found)"
                    )
                return

            try:
                result = await fetch_sitemap(url, client)
            except Exception as e:
                logger.error(f"[scan={scan_id}] Failed to fetch {url}: {e}")
                return

            if result is None:
                logger.warning(f"[scan={scan_id}] No result from {url}")
                return

            raw, content_type = result
            root = parse_xml(raw)
            if root is None:
                logger.warning(f"[scan={scan_id}] Failed to parse XML from {url}")
                return

            if is_sitemap_index(root):
                child_urls = parse_sitemap_index(root)
                logger.info(f"[scan={scan_id}] Sitemap index has {len(child_urls)} children")
                tasks = []
                for child in child_urls:
                    child_resolved = resolve_sitemap_url(url, child)
                    tasks.append(_process(child_resolved, depth + 1))
                if tasks:
                    await asyncio.gather(*tasks)
            else:
                found = parse_urlset(root)
                logger.info(f"[scan={scan_id}] URL set has {len(found)} URLs")
                for u in found:
                    normalized = normalize_url(u)
                    if normalized and is_valid_url(normalized):
                        all_urls.add(normalized)
                
                db.update_scan(
                    scan_id, 
                    phase=f"Fetching sitemaps ({len(all_urls)} URLs found)"
                )

        tasks = []
        for surl in sitemap_urls:
            tasks.append(_process(surl))
        if tasks:
            await asyncio.gather(*tasks)

    logger.info(f"[scan={scan_id}] Extracted {len(all_urls)} URLs from sitemaps")
    return list(all_urls)

