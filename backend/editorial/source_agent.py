"""Source Agent — fetch, parse, detect source type, test sources."""

import logging
import hashlib
import feedparser
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from urllib.parse import urlparse
from datetime import datetime

logger = logging.getLogger(__name__)
REQ_TIMEOUT = 15
HEADERS = {"User-Agent": "BUD-EditorialAgent/1.0"}


def test_source(url: str, source_type: str = "auto") -> Dict:
    """Test a source URL: detect type, fetch preview items."""
    result = {"accessible": False, "detected_type": None, "items_preview": [], "errors": [], "parser_info": ""}

    try:
        resp = requests.get(url, timeout=REQ_TIMEOUT, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            result["errors"].append(f"HTTP {resp.status_code}")
            return result
        result["accessible"] = True
        content = resp.text
        content_type = resp.headers.get("Content-Type", "")
    except Exception as e:
        result["errors"].append(str(e)[:200])
        return result

    # Auto-detect type
    detected = source_type if source_type != "auto" else _detect_type(url, content, content_type)
    result["detected_type"] = detected

    # Parse preview
    if detected == "rss":
        items = _parse_rss(content, url)
        result["parser_info"] = "feedparser (RSS/Atom)"
    elif detected in ("html", "press_room"):
        items = _parse_html(content, url)
        result["parser_info"] = "BeautifulSoup (HTML)"
    else:
        items = _parse_html(content, url)
        result["parser_info"] = f"HTML fallback for {detected}"

    result["items_preview"] = items[:5]
    return result


def fetch_source(url: str, source_type: str) -> List[Dict]:
    """Full fetch of a source. Returns list of raw items."""
    try:
        resp = requests.get(url, timeout=REQ_TIMEOUT, headers=HEADERS, allow_redirects=True)
        if resp.status_code != 200:
            return []
        content = resp.text
    except Exception as e:
        logger.error(f"Fetch failed for {url}: {e}")
        return []

    if source_type == "rss":
        return _parse_rss(content, url)
    else:
        return _parse_html(content, url)


def _detect_type(url: str, content: str, content_type: str) -> str:
    if "xml" in content_type or "rss" in content_type or "atom" in content_type:
        return "rss"
    if content.strip().startswith("<?xml") or "<rss" in content[:500] or "<feed" in content[:500]:
        return "rss"
    if "/feed" in url or "/rss" in url or url.endswith(".xml"):
        return "rss"
    parsed = urlparse(url)
    if "press" in parsed.path.lower() or "noticias" in parsed.path.lower() or "news" in parsed.path.lower():
        return "press_room"
    return "html"


def _parse_rss(content: str, source_url: str) -> List[Dict]:
    feed = feedparser.parse(content)
    items = []
    for entry in feed.entries[:50]:
        pub_date = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_date = datetime(*entry.published_parsed[:6]).isoformat()
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            pub_date = datetime(*entry.updated_parsed[:6]).isoformat()

        summary = ""
        if hasattr(entry, "summary"):
            summary = BeautifulSoup(entry.summary, "html.parser").get_text()[:500]
        elif hasattr(entry, "description"):
            summary = BeautifulSoup(entry.description, "html.parser").get_text()[:500]

        items.append({
            "url": entry.get("link", ""),
            "title_raw": entry.get("title", ""),
            "published_at": pub_date,
            "author": entry.get("author", ""),
            "raw_text": summary,
            "source_url": source_url,
        })
    return items


def _parse_html(content: str, source_url: str) -> List[Dict]:
    soup = BeautifulSoup(content, "html.parser")
    base = urlparse(source_url)
    items = []
    seen = set()

    # Strategy: find article-like elements
    for tag in ["article", "div.post", "div.entry", "li.post-item"]:
        articles = soup.select(tag)
        if articles:
            break
    else:
        # Fallback: find links with substantial text
        articles = []

    if articles:
        for art in articles[:30]:
            link_tag = art.find("a", href=True)
            title_tag = art.find(["h1", "h2", "h3", "h4"])
            if not link_tag:
                continue
            href = link_tag["href"]
            if not href.startswith("http"):
                href = f"{base.scheme}://{base.netloc}{href}"
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
            if not title or len(title) < 10 or href in seen:
                continue
            seen.add(href)
            text = art.get_text(separator=" ", strip=True)[:500]
            items.append({"url": href, "title_raw": title, "published_at": None, "author": "", "raw_text": text, "source_url": source_url})
    else:
        # Fallback: all links in main content
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if len(text) < 20 or not href.startswith("http"):
                continue
            if href in seen:
                continue
            seen.add(href)
            items.append({"url": href, "title_raw": text, "published_at": None, "author": "", "raw_text": text, "source_url": source_url})
            if len(items) >= 20:
                break

    return items


def dedupe_hash(url: str, title: str) -> str:
    raw = f"{url.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def detect_rss(base_url: str) -> Dict:
    """Try to detect RSS/Atom feed for a given URL."""
    parsed = urlparse(base_url)
    candidates = [
        base_url + "feed/", base_url + "feed", base_url + "rss",
        f"{parsed.scheme}://{parsed.netloc}/feed/",
        f"{parsed.scheme}://{parsed.netloc}/feed",
        f"{parsed.scheme}://{parsed.netloc}/rss",
        f"{parsed.scheme}://{parsed.netloc}/rss.xml",
        f"{parsed.scheme}://{parsed.netloc}/atom.xml",
    ]
    # Deduplicate
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    for url in unique:
        try:
            r = requests.get(url, timeout=8, headers=HEADERS, allow_redirects=True)
            if r.status_code == 200 and ("<rss" in r.text[:500] or "<feed" in r.text[:500] or "<?xml" in r.text[:200]):
                feed = feedparser.parse(r.text)
                item_count = len(feed.entries)
                return {
                    "rss_detected": True,
                    "rss_url": url,
                    "rss_validated": item_count > 0,
                    "rss_items_count": item_count,
                    "rss_title": feed.feed.get("title", ""),
                }
        except Exception:
            pass

    return {"rss_detected": False, "rss_url": None, "rss_validated": False}
