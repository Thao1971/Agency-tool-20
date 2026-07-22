"""Enrichment helpers — shared logic to break circular imports between worker and enrichment routes."""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from database import db
from models import now_iso

logger = logging.getLogger(__name__)


def sign_callback(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def build_callback_payload(result: dict, evidence: list) -> dict:
    address = {}
    for k, v in [("street", "address_street"), ("city", "address_city"),
                 ("province", "address_province"), ("postal_code", "postal_code"), ("country", "country")]:
        if result.get(v):
            address[k] = result[v]

    ev_grouped = {}
    for e in evidence:
        f = e.get("field", "other")
        if f not in ev_grouped:
            ev_grouped[f] = []
        ev_grouped[f].append({
            "type": e.get("evidence_type"),
            "source_url": e.get("source_url"),
            "fragment": e.get("fragment"),
            "confidence": e.get("confidence", 0),
            "detected_by": e.get("detected_by")
        })

    conf_cat = result.get("confidence_category", 0) or 0
    conf_overall = result.get("confidence_overall", 0) or 0

    return {
        "consumer_id": result.get("consumer_id"),
        "environment": result.get("environment"),
        "entity_id": result.get("entity_id") or result.get("cis_company_id"),
        "entity_type": result.get("entity_type", "company"),
        "profile_id": result.get("profile_id", "agency_enrichment_v1"),
        "cis_company_id": result.get("cis_company_id") or result.get("entity_id"),
        "cif": result.get("cif"),
        "cif_normalized": result.get("cif_normalized"),
        "input_url": result.get("input_url"),
        "job_id": result.get("job_id"),
        "result_id": result.get("id"),
        "company_name": result.get("company_name"),
        "description": result.get("description"),
        "category": result.get("category"),
        "subcategory": result.get("subcategory"),
        "tags": result.get("tags") or [],
        "address": address or None,
        "main_contact_email": result.get("main_contact_email"),
        "phone": result.get("phone"),
        "has_awards": bool(result.get("has_awards")),
        "awards_evidence": result.get("awards_evidence") or [],
        "main_clients": result.get("main_clients") or [],
        "main_contact_name": result.get("main_contact_name"),
        "main_contact_role": result.get("main_contact_role"),
        "screenshot_path": result.get("screenshot_path"),
        "logo_url": result.get("logo_url"),
        "logo_storage_path": result.get("logo_storage_path"),
        "confidence": {
            "overall": conf_overall,
            "category": conf_cat,
            "subcategory": conf_cat,
            "description": result.get("confidence_description", 0) or 0,
            "clients": result.get("confidence_clients", 0) or 0,
            "contact": result.get("confidence_contact", 0) or 0,
            "awards": result.get("confidence_awards", 0) or 0,
            "address": result.get("confidence_address", 0) or 0
        },
        "evidence": ev_grouped,
        "pages_visited": result.get("visited_pages") or [],
        "status": result.get("status", "completed"),
        "needs_manual_review": conf_cat < 85 or conf_overall < 70,
        "scrape_timestamp": result.get("created_at")
    }


async def fire_enrichment_callback(result_id: str, max_retries: int = 3):
    """Fire callback with HMAC signature and retry. Shared by routes and worker."""
    result = await db.agency_results.find_one({"id": result_id}, {"_id": 0})
    if not result or not result.get("callback_url"):
        return

    evidence = await db.evidence_items.find(
        {"result_id": result_id}, {"_id": 0}
    ).to_list(200)

    payload = build_callback_payload(result, evidence)
    callback_url = result["callback_url"]

    consumer_id = result.get("consumer_id", "default")
    environment = result.get("environment", "production")
    consumer = await db.consumers.find_one({"consumer_id": consumer_id}, {"_id": 0})
    secret = None
    if consumer:
        secret = consumer.get("environments", {}).get(environment, {}).get("callback_secret")

    import requests as req

    payload_bytes = json.dumps(payload, default=str).encode()
    callback_status = "failed"
    last_error = None
    attempt = 0

    for attempt in range(1, max_retries + 1):
        try:
            headers = {"Content-Type": "application/json"}
            if secret:
                sig = sign_callback(payload_bytes, secret)
                headers["X-Scraper-Signature"] = f"sha256={sig}"
            headers["X-Scraper-Timestamp"] = datetime.now(timezone.utc).isoformat()
            headers["X-Scraper-Consumer"] = consumer_id
            headers["X-Scraper-Job-Id"] = result.get("job_id", "")

            resp = req.post(callback_url, data=payload_bytes, headers=headers, timeout=20)
            if resp.status_code < 400:
                callback_status = "sent"
                logger.info(f"Callback sent to {callback_url}: HTTP {resp.status_code} (attempt {attempt}) | entity={result.get('entity_id', '?')}")
                break
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning(f"Callback to {callback_url} returned {resp.status_code} (attempt {attempt}/{max_retries})")
        except Exception as e:
            last_error = str(e)[:300]
            logger.warning(f"Callback to {callback_url} failed (attempt {attempt}/{max_retries}): {e}")

        if attempt < max_retries:
            await asyncio.sleep(2 ** attempt)

    await db.agency_results.update_one(
        {"id": result_id},
        {"$set": {
            "callback_status": callback_status,
            "callback_sent_at": now_iso(),
            "callback_error": last_error if callback_status == "failed" else None,
            "callback_attempts": attempt
        }}
    )
