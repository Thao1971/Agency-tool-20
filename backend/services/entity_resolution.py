"""Entity Resolution Engine — Matches incoming entities against companies_master.

Strategies (in order of priority):
1. CIF exact match
2. Domain exact match
3. Legal name high similarity
4. Commercial name / alias match
5. Fuzzy name match

Thresholds are configurable via DB collection `er_config`.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from urllib.parse import urlparse
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

# Default thresholds (overridden by er_config collection)
DEFAULTS = {
    "auto_merge_threshold": 0.95,
    "conflict_threshold": 0.70,
    "cif_exact_score": 1.0,
    "domain_exact_score": 0.97,
    "legal_name_weight": 0.7,
    "commercial_name_weight": 0.5,
    "alias_weight": 0.6,
}


async def _get_config() -> Dict:
    """Load ER config from DB, with defaults fallback."""
    cfg = await db.er_config.find_one({"config_id": "default"}, {"_id": 0})
    if cfg:
        return {**DEFAULTS, **cfg}
    return DEFAULTS


def _normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    n = name.lower().strip()
    # Remove common suffixes
    for suffix in [' s.l.', ' s.l', ' sl', ' s.a.', ' s.a', ' sa', ' s.l.u.', ' slu',
                   ' s.c.', ' sc', ' ltd', ' inc', ' corp', ' gmbh', ' ag', ' bv',
                   ' group', ' grupo', ' holding']:
        if n.endswith(suffix):
            n = n[:len(n) - len(suffix)].strip()
    # Remove punctuation
    n = re.sub(r'[.,;:!?()"\'\-/&]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _normalize_cif(cif: str) -> Optional[str]:
    if not cif:
        return None
    return re.sub(r'[\s\-\.]', '', cif).upper()


def _extract_domain(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        if not url.startswith("http"):
            url = "https://" + url
        d = urlparse(url).netloc.lower()
        d = re.sub(r'^www\.', '', d)
        return d if d else None
    except Exception:
        return None


def _name_sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


async def resolve_entity(
    legal_name: Optional[str] = None,
    commercial_name: Optional[str] = None,
    cif: Optional[str] = None,
    domain: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    source: str = "unknown",
) -> Dict:
    """
    Resolve an incoming entity against companies_master.
    Returns: {match_id, score, method, status, candidates}
    """
    cfg = await _get_config()
    auto_thresh = cfg["auto_merge_threshold"]
    conflict_thresh = cfg["conflict_threshold"]

    candidates = []
    seen_ids = set()

    cif_norm = _normalize_cif(cif)
    name_norm = _normalize_name(legal_name)
    domain_clean = _extract_domain(domain)

    # ── Strategy 1: CIF exact ──
    if cif_norm:
        matches = await db.companies_master.find(
            {"cif_normalized": cif_norm}, {"_id": 0}
        ).to_list(5)
        for m in matches:
            if m["master_company_id"] not in seen_ids:
                seen_ids.add(m["master_company_id"])
                candidates.append({
                    "master_company_id": m["master_company_id"],
                    "legal_name": m.get("legal_name"),
                    "score": cfg["cif_exact_score"],
                    "method": "cif_exact",
                    "reasons": [f"CIF match: {cif_norm}"],
                })

    # ── Strategy 2: Domain exact ──
    if domain_clean and not candidates:
        matches = await db.companies_master.find(
            {"domain": domain_clean}, {"_id": 0}
        ).to_list(5)
        for m in matches:
            if m["master_company_id"] not in seen_ids:
                seen_ids.add(m["master_company_id"])
                candidates.append({
                    "master_company_id": m["master_company_id"],
                    "legal_name": m.get("legal_name"),
                    "score": cfg["domain_exact_score"],
                    "method": "domain_exact",
                    "reasons": [f"Domain match: {domain_clean}"],
                })

    # ── Strategy 3-5: Name matching ──
    if name_norm and len(name_norm) >= 3 and not any(c["score"] >= auto_thresh for c in candidates):
        prefix = re.escape(name_norm[:min(8, len(name_norm))])
        name_matches = await db.companies_master.find(
            {"normalized_name": {"$regex": prefix, "$options": "i"}}, {"_id": 0}
        ).limit(30).to_list(30)

        for m in name_matches:
            if m["master_company_id"] in seen_ids:
                continue

            best_score = 0.0
            best_method = "fuzzy"
            reasons = []

            # Legal name
            m_norm = m.get("normalized_name", "")
            sim = _name_sim(name_norm, m_norm)
            if sim > best_score:
                best_score = sim * cfg["legal_name_weight"]
                if sim > 0.90:
                    best_score = sim  # High legal name match = strong
                    best_method = "legal_name"
                reasons.append(f"legal_name_sim({sim:.2f})")

            # Commercial names
            for cn in m.get("commercial_names", []):
                cn_norm = _normalize_name(cn)
                cn_sim = _name_sim(name_norm, cn_norm)
                if cn_sim > sim:
                    adj = cn_sim * cfg["commercial_name_weight"]
                    if adj > best_score:
                        best_score = max(best_score, adj)
                        best_method = "commercial_name"
                    reasons.append(f"commercial_name({cn}: {cn_sim:.2f})")

            # Aliases
            for alias in m.get("aliases", []):
                a_norm = _normalize_name(alias)
                a_sim = _name_sim(name_norm, a_norm)
                if a_sim > 0.85:
                    adj = a_sim * cfg["alias_weight"]
                    if adj > best_score:
                        best_score = max(best_score, adj)
                        best_method = "alias"
                    reasons.append(f"alias({alias}: {a_sim:.2f})")

            # Also try incoming commercial_name against master legal
            if commercial_name:
                cn_incoming = _normalize_name(commercial_name)
                cn_sim = _name_sim(cn_incoming, m_norm)
                if cn_sim > best_score:
                    best_score = cn_sim
                    best_method = "commercial_name_reverse"
                    reasons.append(f"incoming_commercial→legal({cn_sim:.2f})")

            if best_score >= conflict_thresh:
                seen_ids.add(m["master_company_id"])
                candidates.append({
                    "master_company_id": m["master_company_id"],
                    "legal_name": m.get("legal_name"),
                    "score": round(best_score, 4),
                    "method": best_method,
                    "reasons": reasons,
                })

    # Sort by score desc
    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates = candidates[:5]

    # Determine status
    if not candidates:
        return {"status": "discovered", "score": 0, "method": None, "match_id": None, "candidates": []}

    best = candidates[0]
    if best["score"] >= auto_thresh:
        return {"status": "auto_merged", "score": best["score"], "method": best["method"],
                "match_id": best["master_company_id"], "candidates": candidates}
    elif best["score"] >= conflict_thresh:
        return {"status": "conflict", "score": best["score"], "method": best["method"],
                "match_id": best["master_company_id"], "candidates": candidates}
    else:
        return {"status": "discovered", "score": best["score"], "method": best["method"],
                "match_id": None, "candidates": candidates}


def _build_signals(name, cif, domain):
    """Build matching signals for an entity."""
    signals = []
    if cif:
        signals.append({"type": "cif", "value": _normalize_cif(cif), "weight": 1.0})
    if domain:
        d = _extract_domain(domain)
        if d:
            signals.append({"type": "domain", "value": d, "weight": 0.97})
    if name:
        signals.append({"type": "name", "value": _normalize_name(name), "weight": 0.7})
    return signals


def _score_to_level(score):
    if score >= 0.95:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


async def create_master_company(
    legal_name: str,
    cif: Optional[str] = None,
    domain: Optional[str] = None,
    commercial_names: Optional[List[str]] = None,
    aliases: Optional[List[str]] = None,
    category_name: Optional[str] = None,
    source: str = "unknown",
    source_id: Optional[str] = None,
    merge_status: str = "discovered",
) -> Dict:
    """Create a new master company record."""
    now = now_iso()
    mc_id = f"mc_{new_id()[:12]}"

    company = {
        "master_company_id": mc_id,
        "legal_name": legal_name,
        "commercial_names": commercial_names or [],
        "aliases": aliases or [],
        "normalized_name": _normalize_name(legal_name),
        "cif": cif,
        "cif_normalized": _normalize_cif(cif),
        "domain": _extract_domain(domain),
        "website": domain,
        "category_name": category_name,
        "source_trace": [{
            "source": source,
            "source_id": source_id,
            "fields_contributed": ["legal_name", "cif", "domain"],
            "confidence": 0.8 if source == "scraper" else 0.9,
            "timestamp": now,
        }],
        "confidence_score": 0.8,
        "confidence_level": "medium",
        "matching_signals": _build_signals(legal_name, cif, domain),
        "merge_status": merge_status,
        "published_to_valuo": False,
        "linked_agency_result_ids": [source_id] if source_id and source == "scraper" else [],
        "linked_transaction_entity_ids": [],
        "created_at": now,
        "updated_at": now,
    }

    await db.companies_master.insert_one({**company})
    return company


async def merge_into_master(
    master_company_id: str,
    incoming: Dict,
    source: str,
    source_id: Optional[str] = None,
    user: Optional[str] = None,
) -> Dict:
    """Merge incoming data into an existing master company."""
    existing = await db.companies_master.find_one(
        {"master_company_id": master_company_id}, {"_id": 0}
    )
    if not existing:
        return {"error": "Master company not found"}

    now = now_iso()
    updates = {}
    fields_updated = []
    fields_rejected = []

    # Merge logic: only update if new data and not overwriting confirmed data
    for field, value in incoming.items():
        if not value:
            continue
        existing_val = existing.get(field)

        if field in ("commercial_names", "aliases"):
            # Append to arrays
            current = set(existing.get(field, []))
            if isinstance(value, list):
                new_items = set(value) - current
            else:
                new_items = {value} - current
            if new_items:
                updates[field] = list(current | new_items)
                fields_updated.append(field)
        elif field == "linked_agency_result_ids":
            current = existing.get(field, [])
            if value not in current:
                updates[field] = current + [value]
                fields_updated.append(field)
        elif not existing_val or (isinstance(existing_val, str) and existing_val.strip().lower() in ("", "unknown", "n/a", "none")):
            # Fill empty or placeholder field
            updates[field] = value
            fields_updated.append(field)
        elif existing_val != value:
            # Conflict — keep existing, log rejection
            fields_rejected.append({"field": field, "existing": existing_val, "incoming": value})

    if updates:
        updates["updated_at"] = now
        # Add source trace
        trace = existing.get("source_trace", [])
        trace.append({
            "source": source,
            "source_id": source_id,
            "fields_contributed": fields_updated,
            "confidence": 0.8,
            "timestamp": now,
        })
        updates["source_trace"] = trace

        # Update confidence based on merge
        merge_score = incoming.get("_merge_score", 0)
        old_confidence = existing.get("confidence_score", 0.5)
        new_confidence = max(old_confidence, merge_score)
        updates["confidence_score"] = round(new_confidence, 4)
        updates["confidence_level"] = _score_to_level(new_confidence)

        # Rebuild matching signals
        signals = existing.get("matching_signals", [])
        for s in _build_signals(incoming.get("legal_name"), incoming.get("cif"), incoming.get("domain") or incoming.get("website")):
            if not any(x["type"] == s["type"] and x["value"] == s["value"] for x in signals):
                signals.append(s)
        updates["matching_signals"] = signals

        await db.companies_master.update_one(
            {"master_company_id": master_company_id},
            {"$set": updates}
        )

    # Audit log
    await db.er_audit_logs.insert_one({
        "log_id": new_id(),
        "master_company_id": master_company_id,
        "action": "merge",
        "source": source,
        "source_id": source_id,
        "fields_updated": fields_updated,
        "fields_rejected": fields_rejected,
        "merge_score": incoming.get("_merge_score", 0),
        "merge_method": incoming.get("_merge_method"),
        "performed_by": user or "system",
        "timestamp": now,
    })

    return {
        "status": "merged",
        "master_company_id": master_company_id,
        "fields_updated": fields_updated,
        "fields_rejected": fields_rejected,
    }
