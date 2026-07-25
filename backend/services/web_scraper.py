"""Web scraper de la web corporativa para enriquecer la descripción de la compañía.

Best-effort y honesto: si el sitio no responde o no hay texto útil devuelve None (nunca
inventa). El parseo (`extract_description`) es puro y testeable sin red. El resultado se
cachea en `master_companies.web_description` para no re-descargar en cada composición.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; ARROBA-bot/1.0; +https://arroba.com)"
_MAX = 600


def normalize_url(url: Optional[str]) -> Optional[str]:
    u = (url or "").strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def extract_description(html: str) -> Optional[str]:
    """Descripción corporativa a partir del HTML: meta description / og:description +
    primeros párrafos relevantes. Función pura (sin red) para poder testearla."""
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    parts = []
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        parts.append(md["content"].strip())
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        parts.append(og["content"].strip())
    for p in soup.find_all("p"):
        t = " ".join(p.get_text(" ").split())
        if 60 <= len(t) <= 400:
            parts.append(t)
        if len(parts) >= 5:
            break

    seen, out = set(), []
    for x in parts:
        k = x.lower()
        if x and k not in seen:
            seen.add(k)
            out.append(x)
    if not out:
        return None
    text = re.sub(r"\s+", " ", " ".join(out)).strip()
    if len(text) > _MAX:
        text = text[:_MAX].rsplit(" ", 1)[0] + "…"
    return text or None


async def fetch_site_description(url: str, timeout: float = 8.0) -> Optional[Dict]:
    """Descarga la home y extrae una descripción. None si falla (guardado)."""
    u = normalize_url(url)
    if not u:
        return None
    try:
        import httpx
        from models import now_iso
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout,
                                     headers={"User-Agent": _UA}) as client:
            r = await client.get(u)
        if r.status_code >= 400 or not r.text:
            return None
        desc = extract_description(r.text)
        if not desc:
            return None
        return {"description": desc, "source_url": str(r.url), "fetched_at": now_iso()}
    except Exception as e:  # noqa: BLE001
        logger.info("web_scraper: no se pudo obtener %s (%s)", u, e)
        return None


async def get_web_description(master_id: str) -> Optional[str]:
    """Descripción de la web corporativa, cacheada en el master. Best-effort."""
    from database import db
    doc = await db.master_companies.find_one(
        {"master_id": master_id}, {"_id": 0, "web_description": 1, "contact.web": 1})
    if not doc:
        return None
    cached = doc.get("web_description")
    if isinstance(cached, dict) and cached.get("description"):
        return cached["description"]
    web = (doc.get("contact") or {}).get("web")
    if not web:
        return None
    res = await fetch_site_description(web)
    if res:
        try:
            await db.master_companies.update_one({"master_id": master_id},
                                                 {"$set": {"web_description": res}})
        except Exception:  # noqa: BLE001
            pass
        return res["description"]
    return None
