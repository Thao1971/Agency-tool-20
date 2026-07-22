"""BORME fetcher — API calls to BOE Open Data + PDF download."""

import logging
import hashlib
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BOE_API_BASE = "https://www.boe.es/datosabiertos/api/borme/sumario"
REQUEST_TIMEOUT = 30
PDF_TIMEOUT = 60


def fetch_summary(date_str: str) -> Optional[Dict]:
    """Fetch BORME summary for a given date (YYYYMMDD). Returns parsed JSON or None."""
    url = f"{BOE_API_BASE}/{date_str}"
    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status", {}).get("code") == "200":
                return data.get("data", {}).get("sumario", {})
            else:
                logger.warning(f"BORME API non-200 status for {date_str}: {data.get('status')}")
                return None
        elif resp.status_code == 404:
            logger.info(f"BORME: No publication for date {date_str} (404)")
            return None
        else:
            logger.warning(f"BORME API HTTP {resp.status_code} for {date_str}")
            return None
    except Exception as e:
        logger.error(f"BORME fetch failed for {date_str}: {e}")
        return None


def extract_items_from_summary(summary: Dict) -> List[Dict]:
    """Extract all items from a summary, tolerant to structure variations."""
    items = []
    diarios = summary.get("diario", [])
    if not isinstance(diarios, list):
        diarios = [diarios]

    pub_date = summary.get("metadatos", {}).get("fecha_publicacion", "")

    for diario in diarios:
        borme_number = diario.get("numero", "")
        sections = diario.get("seccion", [])
        if not isinstance(sections, list):
            sections = [sections]

        for section in sections:
            section_code = section.get("codigo", "")
            section_name = section.get("nombre", "")
            section_items = section.get("item", [])
            if not isinstance(section_items, list):
                section_items = [section_items]

            for item in section_items:
                if not isinstance(item, dict):
                    continue
                pdf_info = item.get("url_pdf", {})
                pdf_url = pdf_info.get("texto", "") if isinstance(pdf_info, dict) else ""

                items.append({
                    "publication_date": pub_date,
                    "borme_number": str(borme_number),
                    "official_identifier": item.get("identificador", ""),
                    "title": item.get("titulo", ""),  # Usually province name
                    "section_code": section_code,
                    "section_name": section_name,
                    "pdf_url": pdf_url,
                    "pdf_size": pdf_info.get("szBytes", "0") if isinstance(pdf_info, dict) else "0",
                })

    return items


def download_pdf(url: str) -> Optional[bytes]:
    """Download PDF from BOE. Returns bytes or None."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=PDF_TIMEOUT, headers={
            "User-Agent": "BUD-AgencyScraper/2.0 (BORME capability)"
        })
        if resp.status_code == 200 and len(resp.content) > 1000:
            return resp.content
        else:
            logger.warning(f"BORME PDF download: HTTP {resp.status_code}, size={len(resp.content)} for {url}")
            return None
    except Exception as e:
        logger.error(f"BORME PDF download failed for {url}: {e}")
        return None


def pdf_hash(content: bytes) -> str:
    """SHA256 hash of PDF content for deduplication."""
    return hashlib.sha256(content).hexdigest()


def date_range(date_from: str, date_to: str) -> List[str]:
    """Generate list of YYYYMMDD strings between two dates."""
    start = datetime.strptime(date_from, "%Y%m%d")
    end = datetime.strptime(date_to, "%Y%m%d")
    dates = []
    current = start
    while current <= end:
        # Skip weekends (BORME only publishes on business days)
        if current.weekday() < 5:
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates
