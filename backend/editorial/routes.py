"""Editorial Intelligence Agent — API routes."""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from database import db
from auth_utils import get_current_user
from models import new_id, now_iso
from editorial import (
    SourceCreate, SourceUpdate, ItemUpdate, DigestCreate, DigestUpdate,
    EDITORIAL_SECTIONS, SECTION_LABELS, ITEM_STATUSES
)
from editorial.source_agent import test_source, dedupe_hash
from editorial.classify_agent import classify_item

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/editorial", tags=["editorial"])


# ══════════════════════════════════════════
# SOURCES
# ══════════════════════════════════════════

@router.get("/sources")
async def list_sources(user=Depends(get_current_user)):
    sources = await db.editorial_sources.find({}, {"_id": 0}).sort("priority", -1).to_list(200)
    return {"sources": sources}

@router.post("/sources")
async def create_source(req: SourceCreate, user=Depends(get_current_user)):
    from urllib.parse import urlparse
    source_id = f"src_{new_id()[:12]}"
    domain = urlparse(req.url).netloc if not req.domain else req.domain
    now = now_iso()
    source = {
        "source_id": source_id, "name": req.name, "url": req.url, "domain": domain,
        "rss_url": req.rss_url, "html_url": req.html_url or req.url,
        "source_type": req.source_type, "source_group": req.source_group,
        "ingestion_mode": req.ingestion_mode,
        "country": req.country, "language": req.language,
        "crawl_frequency": req.crawl_frequency, "target_sections": req.target_sections,
        "priority": req.priority, "active": False, "notes": req.notes,
        "rss_detected": False, "rss_validated": False,
        "status": "new", "last_crawled_at": None, "last_success_at": None, "last_error": None,
        "total_items_generated": 0, "created_by": user.get("email", user["id"]),
        "created_at": now, "updated_at": now,
    }
    await db.editorial_sources.insert_one({**source})
    return source

@router.put("/sources/{source_id}")
async def update_source(source_id: str, req: SourceUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update: raise HTTPException(400, "No fields to update")
    update["updated_at"] = now_iso()
    r = await db.editorial_sources.update_one({"source_id": source_id}, {"$set": update})
    if r.matched_count == 0: raise HTTPException(404, "Source not found")
    return await db.editorial_sources.find_one({"source_id": source_id}, {"_id": 0})

@router.post("/sources/{source_id}/test")
async def test_source_endpoint(source_id: str, user=Depends(get_current_user)):
    source = await db.editorial_sources.find_one({"source_id": source_id}, {"_id": 0})
    if not source: raise HTTPException(404, "Source not found")
    result = test_source(source["url"], source["source_type"])
    return result

@router.post("/sources/test-url")
async def test_url_direct(body: dict, user=Depends(get_current_user)):
    """Test a URL before creating a source."""
    url = body.get("url")
    source_type = body.get("source_type", "auto")
    if not url: raise HTTPException(400, "URL required")
    return test_source(url, source_type)

@router.post("/sources/{source_id}/crawl")
async def crawl_source(source_id: str, user=Depends(get_current_user)):
    source = await db.editorial_sources.find_one({"source_id": source_id}, {"_id": 0})
    if not source: raise HTTPException(404, "Source not found")
    job_id = f"crawl_{new_id()[:12]}"
    job = {
        "job_id": job_id, "source_id": source_id, "source_name": source["name"],
        "crawl_type": "manual", "status": "queued",
        "items_found": 0, "items_new": 0, "items_duplicate": 0, "items_review": 0,
        "error": None, "created_at": now_iso(), "started_at": None, "finished_at": None,
    }
    await db.editorial_jobs.insert_one({**job})
    return {"job_id": job_id, "status": "queued"}

@router.post("/sources/{source_id}/activate")
async def activate_source(source_id: str, user=Depends(get_current_user)):
    await db.editorial_sources.update_one({"source_id": source_id}, {"$set": {"active": True, "updated_at": now_iso()}})
    return {"status": "activated"}

@router.post("/sources/{source_id}/deactivate")
async def deactivate_source(source_id: str, user=Depends(get_current_user)):
    await db.editorial_sources.update_one({"source_id": source_id}, {"$set": {"active": False, "updated_at": now_iso()}})
    return {"status": "deactivated"}

@router.post("/sources/{source_id}/archive")
async def archive_source(source_id: str, user=Depends(get_current_user)):
    await db.editorial_sources.update_one({"source_id": source_id}, {"$set": {"active": False, "status": "archived", "updated_at": now_iso()}})
    return {"status": "archived"}

@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, user=Depends(get_current_user)):
    r = await db.editorial_sources.delete_one({"source_id": source_id})
    if r.deleted_count == 0: raise HTTPException(404, "Source not found")
    return {"status": "deleted"}

@router.post("/sources/{source_id}/analyze")
async def analyze_source(source_id: str, user=Depends(get_current_user)):
    """Auto-detect best ingestion method for a source."""
    from editorial.source_agent import detect_rss, test_source
    source = await db.editorial_sources.find_one({"source_id": source_id}, {"_id": 0})
    if not source: raise HTTPException(404, "Source not found")

    rss_info = detect_rss(source["url"])
    html_test = test_source(source["url"], "html")

    update = {"updated_at": now_iso(), "rss_detected": rss_info["rss_detected"]}
    if rss_info["rss_detected"] and rss_info.get("rss_validated"):
        update["rss_url"] = rss_info["rss_url"]
        update["rss_validated"] = True
        update["ingestion_mode"] = "rss_preferred_html_fallback"
        update["html_url"] = source["url"]
        update["detection_reason"] = f"RSS feed detected and validated ({rss_info.get('rss_items_count', 0)} items)"
        update["ingestion_confidence"] = 0.95
    elif html_test.get("accessible") and html_test.get("items_preview"):
        update["ingestion_mode"] = "html_only"
        update["html_url"] = source["url"]
        update["detection_reason"] = f"No RSS found. HTML accessible ({len(html_test['items_preview'])} items detected)"
        update["ingestion_confidence"] = 0.70
    else:
        update["ingestion_mode"] = "html_only"
        update["status"] = "needs_review"
        update["detection_reason"] = "No RSS and HTML extraction limited"
        update["ingestion_confidence"] = 0.30

    await db.editorial_sources.update_one({"source_id": source_id}, {"$set": update})
    return {**update, "rss_info": rss_info, "html_preview_count": len(html_test.get("items_preview", []))}


# ══════════════════════════════════════════
# EMAIL / NEWSLETTERS
# ══════════════════════════════════════════

@router.get("/email/status")
async def email_status(user=Depends(get_current_user)):
    from editorial.email_agent import check_connection
    status = check_connection()
    processed = await db.editorial_newsletters.count_documents({})
    status["processed_total"] = processed
    return status

@router.post("/email/sync")
async def email_sync(max_emails: int = Query(15), user=Depends(get_current_user)):
    """Sync newsletters from email inbox."""
    from editorial.email_agent import fetch_newsletters
    from editorial.source_agent import dedupe_hash
    from editorial.classify_agent import classify_item
    from editorial.compose_agent import compose_bullet, detect_entities

    newsletters = fetch_newsletters(max_emails=max_emails)
    stats = {"fetched": len(newsletters), "new": 0, "duplicate": 0, "items_created": 0}

    for nl in newsletters:
        existing = await db.editorial_newsletters.find_one({"dedupe_hash": nl["dedupe_hash"]})
        if existing:
            stats["duplicate"] += 1
            continue

        await db.editorial_newsletters.insert_one({
            "id": new_id(), **nl, "status": "processed", "created_at": now_iso()
        })
        stats["new"] += 1

        # Create editorial items from newsletter links
        for link in nl.get("links", [])[:10]:
            dhash = dedupe_hash(link["url"], link["text"])
            if await db.editorial_items.find_one({"dedupe_hash": dhash}):
                continue

            classification = classify_item(link["text"], nl.get("subject", ""))
            composition = compose_bullet(link["text"], classification.get("action_detected"), [])

            item = {
                "item_id": f"edi_{new_id()[:12]}",
                "source_id": "email_newsletter",
                "source_name": f"Newsletter: {nl.get('sender', '')[:30]}",
                "url": link["url"], "canonical_url": link["url"].split("?")[0],
                "title_raw": link["text"], "title_clean": link["text"].strip(),
                "published_at": nl.get("date"), "fetched_at": now_iso(),
                "date_reliable": True, "news_date": nl.get("date") or now_iso(),
                "author": nl.get("sender", ""),
                "raw_text": nl.get("text", "")[:500],
                "summary_short": link["text"][:200],
                "content_type": "newsletter",
                "section_primary": classification["section_primary"],
                "section_secondary": classification.get("section_secondary", []),
                "signal_type": classification.get("signal_type", "other"),
                "action_detected": classification.get("action_detected"),
                "relevance_score": classification.get("confidence_score", 0.5),
                "confidence_score": classification.get("confidence_score", 0.5),
                "classification_method": "rules",
                "dedupe_hash": dhash, "status": "new",
                "editorial_bullet": composition.get("editorial_bullet", link["text"][:100]),
                "anchor_text": composition.get("anchor_text"),
                "entities": [], "facts": [], "digest_ids": [],
                "created_at": now_iso(),
            }
            await db.editorial_items.insert_one({**item})
            stats["items_created"] += 1

    return stats


# ══════════════════════════════════════════
# JOBS
# ══════════════════════════════════════════

@router.get("/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = Query(30, ge=1, le=100), user=Depends(get_current_user)):
    query = {}
    if status: query["status"] = status
    jobs = await db.editorial_jobs.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"jobs": jobs}

@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user=Depends(get_current_user)):
    job = await db.editorial_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job: raise HTTPException(404, "Job not found")
    return job


# ══════════════════════════════════════════
# ITEMS
# ══════════════════════════════════════════

@router.get("/items")
async def list_items(
    status: Optional[str] = None, section: Optional[str] = None,
    source_id: Optional[str] = None, search: Optional[str] = None,
    recent_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    query = {}
    if status: query["status"] = status
    if section: query["section_primary"] = section
    if source_id: query["source_id"] = source_id
    if search: query["$or"] = [
        {"title_clean": {"$regex": search, "$options": "i"}},
        {"editorial_bullet": {"$regex": search, "$options": "i"}}
    ]
    # 7-day window for editorial validity (only for pending/new items)
    if recent_only and (not status or status == "new"):
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        query["news_date"] = {"$gte": cutoff}

    total = await db.editorial_items.count_documents(query)
    items = await db.editorial_items.find(query, {"_id": 0, "raw_text": 0}).sort("news_date", -1).skip(offset).limit(limit).to_list(limit)
    return {"items": items, "total": total}

@router.get("/items/{item_id}")
async def get_item(item_id: str, user=Depends(get_current_user)):
    item = await db.editorial_items.find_one({"item_id": item_id}, {"_id": 0})
    if not item: raise HTTPException(404, "Item not found")
    return item

@router.post("/items/{item_id}/approve")
async def approve_item(item_id: str, user=Depends(get_current_user)):
    await db.editorial_items.update_one({"item_id": item_id}, {"$set": {"status": "approved", "updated_at": now_iso()}})
    return {"status": "approved"}

@router.post("/items/{item_id}/discard")
async def discard_item(item_id: str, user=Depends(get_current_user)):
    await db.editorial_items.update_one({"item_id": item_id}, {"$set": {"status": "discarded", "updated_at": now_iso()}})
    return {"status": "discarded"}

@router.put("/items/{item_id}")
async def edit_item(item_id: str, req: ItemUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    # Track editorial_category changes
    if "editorial_category" in update:
        item = await db.editorial_items.find_one({"item_id": item_id}, {"_id": 0, "ai_suggested_category": 1, "editorial_category": 1})
        if item and update["editorial_category"] != item.get("ai_suggested_category"):
            update["category_changed_by_user"] = True
            update["category_changed_at"] = now_iso()
    update["updated_at"] = now_iso()
    await db.editorial_items.update_one({"item_id": item_id}, {"$set": update})
    return await db.editorial_items.find_one({"item_id": item_id}, {"_id": 0})


@router.post("/items/{item_id}/translate")
async def translate_item_title(item_id: str, user=Depends(get_current_user)):
    """Translate an English title to Spanish using GPT-5.2."""
    item = await db.editorial_items.find_one({"item_id": item_id}, {"_id": 0})
    if not item:
        from fastapi import HTTPException
        raise HTTPException(404, "Item not found")

    title = item.get("title_raw") or item.get("title_clean") or ""
    if not title:
        return {"translated": False, "reason": "no_title"}

    try:
        import os, uuid
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        EKEY = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(api_key=EKEY, session_id=f"translate-{uuid.uuid4()}", system_message="Eres un traductor profesional de titulares de prensa del sector marketing, publicidad y tecnologia. Traduce del ingles al espanol de forma fiel, clara y directa. Devuelve SOLO la traduccion, sin explicaciones ni comillas.")
        chat.with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=f"Traduce este titular al espanol:\n\n{title}"))
        translated = response.strip().strip('"').strip("'")

        await db.editorial_items.update_one(
            {"item_id": item_id},
            {"$set": {
                "title_translated_es": translated,
                "title_language": "en",
                "updated_at": now_iso(),
            }}
        )
        return {"translated": True, "title_translated_es": translated}
    except Exception as e:
        logger.error(f"Translation failed for {item_id}: {e}")
        return {"translated": False, "reason": str(e)[:200]}


@router.get("/sections")
async def get_editorial_sections():
    """Return available editorial sections with labels and emojis."""
    from editorial import EDITORIAL_SECTIONS, SECTION_LABELS, SECTION_EMOJIS
    return {"sections": [
        {"key": s, "label": SECTION_LABELS.get(s, s), "emoji": SECTION_EMOJIS.get(s, ""), "display": f"{SECTION_LABELS.get(s, s)} {SECTION_EMOJIS.get(s, '')}"}
        for s in EDITORIAL_SECTIONS
    ]}

@router.post("/items/{item_id}/mark-for-digest")
async def mark_for_digest(item_id: str, body: dict, user=Depends(get_current_user)):
    digest_id = body.get("digest_id")
    await db.editorial_items.update_one(
        {"item_id": item_id},
        {"$set": {"status": "added_to_digest"}, "$addToSet": {"digest_ids": digest_id}}
    )
    return {"status": "added_to_digest"}


# ══════════════════════════════════════════
# DIGESTS
# ══════════════════════════════════════════

@router.get("/digests")
async def list_digests(user=Depends(get_current_user)):
    digests = await db.editorial_digests.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"digests": digests}

@router.post("/digests")
async def create_digest(req: DigestCreate, user=Depends(get_current_user)):
    from editorial import ADCEO_DEFAULT_INTRO
    digest_id = f"dig_{new_id()[:12]}"
    digest = {
        "digest_id": digest_id, "week_label": req.week_label, "title": req.title,
        "intro_text": req.intro_text or ADCEO_DEFAULT_INTRO,
        "selected_item_ids": [], "section_order": list(EDITORIAL_SECTIONS),
        "manual_blocks": {},  # e.g. {"palabra_de_dani": "...", "mirada_control": "..."}
        "status": "draft", "created_by": user.get("email", user["id"]),
        "markdown_output": None, "html_output": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.editorial_digests.insert_one({**digest})
    return digest

@router.get("/digests/{digest_id}")
async def get_digest(digest_id: str, user=Depends(get_current_user)):
    digest = await db.editorial_digests.find_one({"digest_id": digest_id}, {"_id": 0})
    if not digest: raise HTTPException(404, "Digest not found")
    # Load items
    if digest.get("selected_item_ids"):
        items = await db.editorial_items.find(
            {"item_id": {"$in": digest["selected_item_ids"]}},
            {"_id": 0, "raw_text": 0}
        ).to_list(200)
        digest["items"] = items
    return digest

@router.put("/digests/{digest_id}")
async def update_digest(digest_id: str, req: DigestUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    update["updated_at"] = now_iso()
    await db.editorial_digests.update_one({"digest_id": digest_id}, {"$set": update})
    return await db.editorial_digests.find_one({"digest_id": digest_id}, {"_id": 0})

@router.post("/digests/{digest_id}/generate-output")
async def generate_digest_output(digest_id: str, user=Depends(get_current_user)):
    from editorial import SECTION_EMOJIS, MANUAL_SECTIONS
    digest = await db.editorial_digests.find_one({"digest_id": digest_id}, {"_id": 0})
    if not digest: raise HTTPException(404, "Digest not found")

    items = await db.editorial_items.find(
        {"item_id": {"$in": digest.get("selected_item_ids", [])}},
        {"_id": 0}
    ).to_list(200)

    by_section = {}
    for item in items:
        sec = item.get("section_primary", "noticias_semana")
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(item)

    manual_blocks = digest.get("manual_blocks", {})
    section_order = digest.get("section_order", EDITORIAL_SECTIONS)

    # Build HTML (Substack-ready)
    html_parts = []
    # Intro
    if digest.get("intro_text"):
        intro_html = digest["intro_text"].replace("\n\n", "</p><p>").replace("\n", "<br/>")
        html_parts.append(f"<p>{intro_html}</p><hr/>")

    for section_key in section_order:
        label = SECTION_LABELS.get(section_key, section_key)
        emoji = SECTION_EMOJIS.get(section_key, "")
        section_items = by_section.get(section_key, [])
        manual_text = manual_blocks.get(section_key, "")

        # Always show section heading (even if empty)
        html_parts.append(f"<h3>{label} {emoji}</h3>")

        # Manual block content
        if manual_text:
            manual_html = manual_text.replace("\n\n", "</p><p>").replace("\n", "<br/>")
            html_parts.append(f"<p>{manual_html}</p>")

        # Auto items
        for item in section_items:
            bullet = item.get("editorial_bullet") or item.get("title_clean", "")
            url = item.get("url", "")
            anchor = item.get("anchor_text")

            # Anchor must be short (max 3 words) and present in bullet
            if anchor and url and anchor in bullet and len(anchor.split()) <= 3:
                linked = bullet.replace(anchor, f'<a href="{url}">{anchor}</a>', 1)
                html_parts.append(f"<p>{linked}</p>")
            elif url:
                # Fallback: try to find a short verb in the bullet
                fallback_anchor = _find_short_anchor(bullet)
                if fallback_anchor and fallback_anchor in bullet:
                    linked = bullet.replace(fallback_anchor, f'<a href="{url}">{fallback_anchor}</a>', 1)
                    html_parts.append(f"<p>{linked}</p>")
                else:
                    # Last resort: link first 3 words
                    words = bullet.split()
                    if len(words) > 3:
                        short = " ".join(words[:3])
                        rest = " ".join(words[3:])
                        html_parts.append(f'<p><a href="{url}">{short}</a> {rest}</p>')
                    else:
                        html_parts.append(f'<p><a href="{url}">{bullet}</a></p>')
            else:
                html_parts.append(f"<p>{bullet}</p>")

    html = "\n".join(html_parts)

    # Build Markdown
    md_parts = []
    if digest.get("intro_text"):
        md_parts.append(f"{digest['intro_text']}\n\n---\n")
    for section_key in section_order:
        label = SECTION_LABELS.get(section_key, section_key)
        emoji = SECTION_EMOJIS.get(section_key, "")
        section_items = by_section.get(section_key, [])
        manual_text = manual_blocks.get(section_key, "")
        # Always show section heading
        md_parts.append(f"\n## {label} {emoji}\n")
        if manual_text:
            md_parts.append(f"{manual_text}\n")
        for item in section_items:
            bullet = item.get("editorial_bullet") or item.get("title_clean", "")
            md_parts.append(f"{bullet}\n")
    markdown = "\n".join(md_parts)

    await db.editorial_digests.update_one(
        {"digest_id": digest_id},
        {"$set": {"markdown_output": markdown, "html_output": html, "status": "generated", "updated_at": now_iso()}}
    )
    return {"markdown": markdown, "html": html, "items_count": len(items), "sections_count": len(by_section)}


def _find_short_anchor(text: str) -> str:
    """Find a short action verb in text to use as anchor."""
    import re
    verbs = [
        "compra", "adquiere", "lanza", "presenta", "nombra", "gana", "abre",
        "factura", "crece", "firma", "cierra", "vende", "fusiona", "inaugura",
        "reduce", "capta", "invierte", "ficha", "incorpora", "anuncia",
        "amplia", "entra", "sale", "lidera", "supera", "alcanza",
    ]
    text_lower = text.lower()
    for v in verbs:
        match = re.search(rf'\b({v}\w*)\b', text_lower)
        if match:
            # Return the original-case version
            start, end = match.start(), match.end()
            return text[start:end]
    return None


# ══════════════════════════════════════════
# HEALTH / LOGS
# ══════════════════════════════════════════

@router.get("/health")
async def editorial_health(user=Depends(get_current_user)):
    sources_total = await db.editorial_sources.count_documents({})
    sources_active = await db.editorial_sources.count_documents({"active": True})
    items_total = await db.editorial_items.count_documents({})
    items_new = await db.editorial_items.count_documents({"status": "new"})
    items_approved = await db.editorial_items.count_documents({"status": "approved"})
    digests_total = await db.editorial_digests.count_documents({})
    jobs_total = await db.editorial_jobs.count_documents({})

    return {
        "sources": {"total": sources_total, "active": sources_active},
        "items": {"total": items_total, "new": items_new, "approved": items_approved},
        "digests": {"total": digests_total},
        "jobs": {"total": jobs_total},
        "sections": SECTION_LABELS,
    }


@router.post("/sources/preload")
async def preload_sources(user=Depends(get_current_user)):
    """Preload classified sources from curated bookmark data (Ola 1: clean sources only)."""
    from urllib.parse import urlparse

    PRELOAD = [
        # ── marketing_advertising_media ──
        {"name": "The Drum", "url": "https://www.thedrum.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "UK", "priority": 8, "target_sections": ["noticias_semana", "nombramientos_reconocimientos"]},
        {"name": "Campaign", "url": "https://www.campaignlive.co.uk/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "UK", "priority": 7},
        {"name": "Anuncios.com", "url": "https://www.anuncios.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 8, "target_sections": ["noticias_semana", "nombramientos_reconocimientos"]},
        {"name": "PRNoticias", "url": "https://prnoticias.com/feed/", "source_type": "rss", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 8},
        {"name": "Marketing Brew", "url": "https://www.marketingbrew.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "US", "priority": 7},
        {"name": "Ad Age", "url": "https://adage.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "US", "priority": 8},
        {"name": "Digiday", "url": "https://digiday.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "US", "priority": 7},
        {"name": "AdExchanger", "url": "https://www.adexchanger.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "US", "priority": 6},
        {"name": "ExchangeWire", "url": "https://www.exchangewire.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "en", "country": "UK", "priority": 6},
        {"name": "Adlatina", "url": "https://www.adlatina.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "LATAM", "priority": 5},
        {"name": "IPMark", "url": "https://ipmark.com/feed/", "source_type": "rss", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 8},
        {"name": "DigiMedios", "url": "https://digimedios.es/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 6},
        {"name": "Espacio Dircom", "url": "https://www.espaciodircom.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 6},
        {"name": "Programmatic Spain", "url": "https://www.programaticaly.com/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 6},
        {"name": "Periodico PublicidAD M&A", "url": "https://www.periodicopublicidad.com/blog/section/fusiones-y-adquisiciones/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 7},
        {"name": "Enfoque AV", "url": "https://enfoqueav.es/industria/", "source_type": "html", "source_group": "marketing_advertising_media", "language": "es", "country": "ES", "priority": 5},
        # ── technology_startups_adtech ──
        {"name": "Tech.eu", "url": "https://tech.eu/", "source_type": "html", "source_group": "technology_startups_adtech", "language": "en", "country": "EU", "priority": 7},
        {"name": "Business Insider ES Tech", "url": "https://www.businessinsider.es/tecnologia", "source_type": "html", "source_group": "technology_startups_adtech", "language": "es", "country": "ES", "priority": 7},
        {"name": "Ecommerce News", "url": "https://ecommerce-news.es/", "source_type": "html", "source_group": "technology_startups_adtech", "language": "es", "country": "ES", "priority": 6},
        {"name": "WIRED ES", "url": "https://es.wired.com/", "source_type": "html", "source_group": "technology_startups_adtech", "language": "es", "country": "ES", "priority": 6},
        # ── ma_pe_vc_corporate_finance ──
        {"name": "El Referente", "url": "https://elreferente.es/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 8},
        {"name": "FinanceCommunity ES", "url": "https://financecommunity.es/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 7},
        {"name": "Capital & Corporate", "url": "https://www.capitalcorporate.com/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 7},
        {"name": "Expansion M&A", "url": "https://www.expansion.com/empresas/fusiones-y-adquisiciones.html", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 8},
        {"name": "Forbes ES Empresas", "url": "https://forbes.es/seccion/empresas/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 7},
        {"name": "El Confidencial Empresas", "url": "https://www.elconfidencial.com/empresas/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 7},
        {"name": "TechCrunch VC", "url": "https://techcrunch.com/category/venture/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "en", "country": "US", "priority": 8},
        {"name": "Dealflow ES", "url": "https://dealflow.es/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 8},
        {"name": "Sifted", "url": "https://sifted.eu/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "en", "country": "EU", "priority": 7},
        {"name": "Adweek M&A", "url": "https://www.adweek.com/category/mergers-acquisitions/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "en", "country": "US", "priority": 7},
        {"name": "The Officer", "url": "https://theofficer.es/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 6},
        {"name": "Cinco Dias Startups", "url": "https://cincodias.elpais.com/noticias/empresas-emergentes/", "source_type": "html", "source_group": "ma_pe_vc_corporate_finance", "language": "es", "country": "ES", "priority": 6},
    ]

    loaded = 0; skipped = 0
    for src in PRELOAD:
        domain = urlparse(src["url"]).netloc
        existing = await db.editorial_sources.find_one({"domain": domain})
        if existing:
            skipped += 1
            continue
        source_id = f"src_{new_id()[:12]}"
        now = now_iso()
        await db.editorial_sources.insert_one({
            "source_id": source_id, "name": src["name"], "url": src["url"], "domain": domain,
            "source_type": src["source_type"], "source_group": src.get("source_group", "needs_review"),
            "country": src.get("country", "ES"), "language": src.get("language", "es"),
            "crawl_frequency": "12h", "target_sections": src.get("target_sections", []),
            "priority": src.get("priority", 5), "active": False, "notes": None,
            "status": "new", "last_crawled_at": None, "last_success_at": None, "last_error": None,
            "total_items_generated": 0, "needs_review": False,
            "created_by": user.get("email", user["id"]), "created_at": now, "updated_at": now,
        })
        loaded += 1

    return {"loaded": loaded, "skipped": skipped, "total": len(PRELOAD),
            "groups": {"marketing_advertising_media": 16, "technology_startups_adtech": 4, "ma_pe_vc_corporate_finance": 12}}



@router.post("/sources/scan-rss")
async def scan_rss_all(user=Depends(get_current_user)):
    """Scan all sources for RSS feeds and update their rss_url field."""
    from editorial.source_agent import detect_rss
    sources = await db.editorial_sources.find({}, {"_id": 0}).to_list(200)
    results = {"scanned": 0, "rss_found": 0, "html_only": 0, "sources": []}

    for source in sources:
        if source.get("rss_url") and source.get("rss_validated"):
            results["rss_found"] += 1
            results["sources"].append({"name": source["name"], "status": "already_verified", "rss_url": source["rss_url"]})
            continue

        rss_info = detect_rss(source["url"])
        results["scanned"] += 1

        update = {
            "rss_detected": rss_info["rss_detected"],
            "rss_validated": rss_info.get("rss_validated", False),
            "updated_at": now_iso(),
        }

        if rss_info["rss_detected"] and rss_info.get("rss_validated"):
            update["rss_url"] = rss_info["rss_url"]
            update["ingestion_mode"] = "rss_preferred_html_fallback"
            update["html_url"] = source["url"]
            results["rss_found"] += 1
            results["sources"].append({"name": source["name"], "status": "rss_verified", "rss_url": rss_info["rss_url"], "items": rss_info.get("rss_items_count", 0)})
        else:
            update["ingestion_mode"] = "html_only"
            results["html_only"] += 1
            results["sources"].append({"name": source["name"], "status": "html_only"})

        await db.editorial_sources.update_one({"source_id": source["source_id"]}, {"$set": update})

    return results
