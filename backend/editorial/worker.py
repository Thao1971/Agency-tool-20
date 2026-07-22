"""Editorial Worker — MongoDB polling for crawl jobs."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from database import db
from models import new_id, now_iso
from editorial.source_agent import fetch_source, dedupe_hash
from editorial.classify_agent import classify_item
from editorial.compose_agent import compose_bullet, detect_entities, detect_facts

logger = logging.getLogger(__name__)

_running = False
POLL_INTERVAL = 5

# Simple language detection for titles
_EN_WORDS = {'the', 'and', 'for', 'with', 'new', 'has', 'its', 'from', 'will', 'how', 'why', 'launches', 'acquires', 'announces', 'reports', 'partners', 'unveils', 'opens', 'plans', 'aims', 'after', 'into', 'their', 'global', 'year', 'growth', 'about', 'been', 'are', 'was', 'were', 'that', 'this', 'what', 'says', 'named', 'unit', 'revenue', 'deal', 'firm', 'raises', 'buys', 'joins', 'expands', 'hits', 'amid', 'over', 'could', 'across', 'through', 'between'}

def _detect_language(title: str) -> str:
    """Detect if title is English or Spanish. Returns 'en' or 'es'."""
    if not title:
        return "es"
    words = set(re.findall(r'[a-zA-Z]+', title.lower()))
    en_count = len(words & _EN_WORDS)
    # Also check for Spanish indicators
    es_words = {'de', 'la', 'el', 'en', 'los', 'las', 'por', 'con', 'del', 'para', 'una', 'nuevo', 'nueva', 'adquiere', 'lanza', 'anuncia', 'resultado', 'millones', 'empresa', 'sector'}
    es_count = len(words & es_words)
    if es_count >= 2:
        return "es"
    return "en" if en_count >= 2 else "es"


async def start_editorial_worker():
    global _running
    if _running:
        return
    _running = True
    logger.info("Editorial worker started")
    asyncio.create_task(_worker_loop())


async def _worker_loop():
    global _running
    while _running:
        try:
            job = await db.editorial_jobs.find_one_and_update(
                {"status": "queued"},
                {"$set": {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}},
                sort=[("created_at", 1)],
                return_document=True
            )
            if not job:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            await _process_crawl_job(job)
        except Exception as e:
            logger.error(f"Editorial worker error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


async def _process_crawl_job(job: dict):
    job_id = job["job_id"]
    source_id = job["source_id"]

    try:
        source = await db.editorial_sources.find_one({"source_id": source_id}, {"_id": 0})
        if not source:
            raise ValueError(f"Source {source_id} not found")

        logger.info(f"Editorial crawl: {source['name']} ({source['url'][:50]})")

        # RSS-first ingestion strategy
        ingestion_mode = source.get("ingestion_mode", "rss_preferred_html_fallback")
        rss_url = source.get("rss_url")
        html_url = source.get("html_url") or source.get("url")
        used_method = None

        if ingestion_mode in ("rss_only", "rss_preferred_html_fallback") and rss_url:
            raw_items = fetch_source(rss_url, "rss")
            if raw_items:
                used_method = "rss"
            elif ingestion_mode == "rss_preferred_html_fallback":
                raw_items = fetch_source(html_url, "html")
                used_method = "html_fallback"
            else:
                raw_items = []
                used_method = "rss_failed"
        elif ingestion_mode == "html_only" or not rss_url:
            raw_items = fetch_source(html_url, source.get("source_type", "html"))
            used_method = "html"
        else:
            raw_items = fetch_source(source["url"], source.get("source_type", "html"))
            used_method = "default"

        stats = {"items_found": len(raw_items), "items_new": 0, "items_duplicate": 0, "items_review": 0, "ingestion_method": used_method}

        await db.editorial_jobs.update_one(
            {"job_id": job_id}, {"$set": {"status": "parsed", "items_found": len(raw_items)}}
        )

        for raw in raw_items:
            if not raw.get("title_raw") or not raw.get("url"):
                continue

            # Dedupe
            dhash = dedupe_hash(raw["url"], raw["title_raw"])
            existing = await db.editorial_items.find_one({"dedupe_hash": dhash})
            if existing:
                stats["items_duplicate"] += 1
                continue

            # Classify
            classification = classify_item(raw["title_raw"], raw.get("raw_text", ""))

            # Detect entities and facts
            entities = detect_entities(raw["title_raw"], raw.get("raw_text", ""))
            facts = detect_facts(raw["title_raw"], raw.get("raw_text", ""))

            # Compose bullet
            composition = compose_bullet(
                raw["title_raw"],
                classification.get("action_detected"),
                entities
            )

            # Build item
            item = {
                "item_id": f"edi_{new_id()[:12]}",
                "source_id": source_id,
                "source_name": source["name"],
                "url": raw["url"],
                "canonical_url": raw["url"].split("?")[0].split("#")[0],
                "title_raw": raw["title_raw"],
                "title_clean": raw["title_raw"].strip(),
                "title_language": _detect_language(raw["title_raw"]),
                "title_translated_es": None,
                "published_at": raw.get("published_at"),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "date_reliable": raw.get("published_at") is not None,
                "news_date": raw.get("published_at") or datetime.now(timezone.utc).isoformat(),
                "author": raw.get("author", ""),
                "raw_text": raw.get("raw_text", "")[:2000],
                "summary_short": raw.get("raw_text", "")[:200],
                "content_type": "article",
                "section_primary": classification["section_primary"],
                "ai_suggested_category": classification["section_primary"],
                "editorial_category": classification["section_primary"],
                "category_changed_by_user": False,
                "section_secondary": classification.get("section_secondary", []),
                "signal_type": classification.get("signal_type", "other"),
                "action_detected": classification.get("action_detected"),
                "country": source.get("country", "ES"),
                "language": source.get("language", "es"),
                "relevance_score": classification.get("confidence_score", 0.5),
                "confidence_score": classification.get("confidence_score", 0.5),
                "classification_method": classification.get("classification_method", "rules"),
                "classification_evidence": classification.get("classification_evidence", []),
                "dedupe_hash": dhash,
                "status": "new",
                "editorial_bullet": composition.get("editorial_bullet", ""),
                "anchor_text": composition.get("anchor_text"),
                "entities": entities,
                "facts": facts,
                "digest_ids": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            await db.editorial_items.insert_one({**item})
            stats["items_new"] += 1

        # Update job
        await db.editorial_jobs.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "completed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                **stats
            }}
        )

        # Update source
        await db.editorial_sources.update_one(
            {"source_id": source_id},
            {"$set": {
                "last_crawled_at": datetime.now(timezone.utc).isoformat(),
                "last_success_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
                "status": "healthy",
                "total_items_generated": await db.editorial_items.count_documents({"source_id": source_id})
            }}
        )

        logger.info(f"Editorial crawl done: {source['name']} — {stats['items_new']} new, {stats['items_duplicate']} dupes")

    except Exception as e:
        logger.error(f"Editorial crawl failed: {e}")
        await db.editorial_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(e)[:500], "finished_at": datetime.now(timezone.utc).isoformat()}}
        )
        await db.editorial_sources.update_one(
            {"source_id": source_id},
            {"$set": {"last_error": str(e)[:500], "status": "error"}}
        )


async def stop_editorial_worker():
    global _running
    _running = False
