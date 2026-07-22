"""Entity Matching Engine — Conservative matching of transaction entities against CIS companies.

Rules:
- CIF exact match → auto_strong_candidate
- Domain exact match → auto_strong_candidate
- Name very high (>0.90) + country match + additional signal → auto_strong_candidate
- Name fuzzy alone (even >0.90) → auto_ambiguous_candidate (fuzzy never resolves by itself)
- Name moderate (0.60-0.90) → auto_ambiguous_candidate
- Below 0.60 → not a candidate
"""

import re
import logging
from typing import List, Dict, Optional
from difflib import SequenceMatcher
from urllib.parse import urlparse
from transactions import normalize_name

logger = logging.getLogger(__name__)

ENTITY_ROLES = ["target", "buyer", "seller", "investor", "advisor", "source_entity"]

MATCH_STATUSES = [
    "auto_strong_candidate",
    "auto_ambiguous_candidate",
    "unmatched",
    "manual_confirmed",
    "manual_rejected",
    "needs_new_company",
]

MATCH_METHODS = ["cif_exact", "domain_exact", "name_fuzzy_strong", "name_fuzzy_moderate", "manual"]


def extract_domain(url: str) -> Optional[str]:
    """Extract clean domain from URL."""
    if not url:
        return None
    try:
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain = re.sub(r'^www\.', '', domain)
        return domain if domain else None
    except Exception:
        return None


def _name_similarity(a: str, b: str) -> float:
    """Compare two normalized names."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _normalize_cif(cif: str) -> Optional[str]:
    """Normalize CIF for comparison."""
    if not cif:
        return None
    return re.sub(r'[\s\-\.]', '', cif).upper()


async def find_entity_matches(
    db,
    raw_name: str,
    raw_cif: Optional[str] = None,
    raw_url: Optional[str] = None,
    geography: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = 5
) -> List[Dict]:
    """
    Search agency_results for potential matches against an entity.
    Returns a list of candidates sorted by confidence, with match_status and reasons.
    """
    candidates = []
    seen_ids = set()
    name_norm = normalize_name(raw_name) if raw_name else ""
    cif_norm = _normalize_cif(raw_cif)
    domain = extract_domain(raw_url)

    # ─── Strategy 1: CIF exact match ───
    if cif_norm:
        cif_results = await db.agency_results.find(
            {"cif_normalized": cif_norm, "status": "completed"},
            {"_id": 0, "id": 1, "company_name": 1, "input_url": 1, "cif": 1,
             "cif_normalized": 1, "category": 1, "subcategory": 1, "country": 1,
             "cis_company_id": 1}
        ).to_list(5)

        for r in cif_results:
            if r["id"] in seen_ids:
                continue
            seen_ids.add(r["id"])
            candidates.append({
                "company_id": r["id"],
                "cis_company_id": r.get("cis_company_id"),
                "company_name": r.get("company_name"),
                "company_url": r.get("input_url"),
                "company_cif": r.get("cif"),
                "company_category": r.get("category"),
                "company_country": r.get("country"),
                "match_confidence": 0.98,
                "match_status": "auto_strong_candidate",
                "match_method": "cif_exact",
                "match_reasons": [f"CIF exact: {cif_norm}"],
            })

    # ─── Strategy 2: Domain exact match ───
    if domain:
        domain_regex = re.escape(domain)
        domain_results = await db.agency_results.find(
            {"input_url": {"$regex": domain_regex, "$options": "i"}, "status": "completed"},
            {"_id": 0, "id": 1, "company_name": 1, "input_url": 1, "cif": 1,
             "cif_normalized": 1, "category": 1, "subcategory": 1, "country": 1,
             "cis_company_id": 1}
        ).to_list(5)

        for r in domain_results:
            if r["id"] in seen_ids:
                continue
            r_domain = extract_domain(r.get("input_url", ""))
            if r_domain and r_domain == domain:
                seen_ids.add(r["id"])
                candidates.append({
                    "company_id": r["id"],
                    "cis_company_id": r.get("cis_company_id"),
                    "company_name": r.get("company_name"),
                    "company_url": r.get("input_url"),
                    "company_cif": r.get("cif"),
                    "company_category": r.get("category"),
                    "company_country": r.get("country"),
                    "match_confidence": 0.95,
                    "match_status": "auto_strong_candidate",
                    "match_method": "domain_exact",
                    "match_reasons": [f"Domain exact: {domain}"],
                })

    # ─── Strategy 3: Name fuzzy match ───
    if name_norm and len(name_norm) >= 3:
        # Use first significant token(s) for initial filter
        search_prefix = name_norm[:min(8, len(name_norm))]
        name_results = await db.agency_results.find(
            {"company_name": {"$regex": search_prefix, "$options": "i"}, "status": "completed"},
            {"_id": 0, "id": 1, "company_name": 1, "input_url": 1, "cif": 1,
             "cif_normalized": 1, "category": 1, "subcategory": 1, "country": 1,
             "cis_company_id": 1}
        ).to_list(50)

        for r in name_results:
            if r["id"] in seen_ids:
                continue
            r_name_norm = normalize_name(r.get("company_name", ""))
            if not r_name_norm:
                continue

            sim = _name_similarity(name_norm, r_name_norm)
            if sim < 0.60:
                continue

            reasons = [f"name_similarity({sim:.2f})"]
            confidence = sim * 0.7  # Name alone caps at 0.7 * sim

            # Boost: country match
            country_match = False
            if geography and r.get("country"):
                geo_norm = geography.strip().lower()
                co_norm = r["country"].strip().lower()
                if geo_norm == co_norm or geo_norm in co_norm or co_norm in geo_norm:
                    country_match = True
                    confidence += 0.10
                    reasons.append(f"country_match({r['country']})")

            # Boost: sector/category overlap
            sector_match = False
            if sector and r.get("category"):
                sec_norm = normalize_name(sector)
                cat_norm = normalize_name(r["category"])
                sec_sim = _name_similarity(sec_norm, cat_norm)
                if sec_sim > 0.50:
                    sector_match = True
                    confidence += 0.05
                    reasons.append(f"sector_overlap({sec_sim:.2f})")

            # Determine status: strong ONLY if name very high + country + additional signal
            if sim >= 0.92 and country_match and (sector_match or cif_norm):
                match_status = "auto_strong_candidate"
                match_method = "name_fuzzy_strong"
                confidence = min(confidence + 0.05, 0.94)
            else:
                match_status = "auto_ambiguous_candidate"
                match_method = "name_fuzzy_moderate"

            confidence = round(min(confidence, 0.99), 3)

            seen_ids.add(r["id"])
            candidates.append({
                "company_id": r["id"],
                "cis_company_id": r.get("cis_company_id"),
                "company_name": r.get("company_name"),
                "company_url": r.get("input_url"),
                "company_cif": r.get("cif"),
                "company_category": r.get("category"),
                "company_country": r.get("country"),
                "match_confidence": confidence,
                "match_status": match_status,
                "match_method": match_method,
                "match_reasons": reasons,
            })

    # Sort by confidence desc, limit results
    candidates.sort(key=lambda c: c["match_confidence"], reverse=True)
    return candidates[:limit]


async def run_matching_for_transaction(db, tx: Dict) -> List[Dict]:
    """
    Run entity matching for all roles in a transaction.
    Creates/updates transaction_company_links entries.
    Returns list of created links.
    """
    from models import new_id, now_iso

    roles = [
        ("target", tx.get("target_name"), None),
        ("buyer", tx.get("buyer_name"), None),
        ("seller", tx.get("seller_name"), None),
    ]

    tx_id = tx["transaction_id"]
    geography = tx.get("geography_primary")
    sector = tx.get("sector_original") or tx.get("cis_category_suggested")
    source_url = tx.get("source_url")
    now = now_iso()
    links_created = []

    for role, raw_name, raw_cif in roles:
        if not raw_name or not raw_name.strip():
            continue

        # Check if link already exists for this role
        existing = await db.transaction_company_links.find_one(
            {"transaction_id": tx_id, "entity_role": role}
        )
        if existing and existing.get("match_status") in ("manual_confirmed", "manual_rejected", "needs_new_company"):
            continue  # Don't overwrite human decisions

        candidates = await find_entity_matches(
            db, raw_name=raw_name, raw_cif=raw_cif,
            raw_url=source_url, geography=geography, sector=sector, limit=3
        )

        if existing:
            # Update existing link with best match
            if candidates:
                best = candidates[0]
                await db.transaction_company_links.update_one(
                    {"link_id": existing["link_id"]},
                    {"$set": {
                        "matched_company_id": best["company_id"],
                        "matched_company_name": best["company_name"],
                        "matched_company_url": best.get("company_url"),
                        "matched_cis_company_id": best.get("cis_company_id"),
                        "match_status": best["match_status"],
                        "match_confidence": best["match_confidence"],
                        "match_reasons": best["match_reasons"],
                        "match_method": best["match_method"],
                        "all_candidates": candidates,
                        "updated_at": now,
                    }}
                )
            continue

        # Create new link
        link_id = f"lnk_{new_id()[:12]}"
        best = candidates[0] if candidates else None

        link = {
            "link_id": link_id,
            "transaction_id": tx_id,
            "entity_role": role,
            "raw_entity_name": raw_name,
            "raw_entity_cif": raw_cif,
            "matched_company_id": best["company_id"] if best else None,
            "matched_company_name": best["company_name"] if best else None,
            "matched_company_url": best.get("company_url") if best else None,
            "matched_cis_company_id": best.get("cis_company_id") if best else None,
            "match_status": best["match_status"] if best else "unmatched",
            "match_confidence": best["match_confidence"] if best else 0.0,
            "match_reasons": best["match_reasons"] if best else [],
            "match_method": best["match_method"] if best else None,
            "all_candidates": candidates,
            "confirmed_by": None,
            "confirmed_at": None,
            "created_at": now,
            "updated_at": now,
        }

        await db.transaction_company_links.insert_one({**link})
        links_created.append(link)

    # Update transaction matching_status
    links = await db.transaction_company_links.find(
        {"transaction_id": tx_id}, {"_id": 0, "match_status": 1}
    ).to_list(10)

    if not links:
        status = "no_entities"
    elif all(lnk["match_status"] in ("manual_confirmed", "auto_strong_candidate") for lnk in links):
        status = "completed"
    elif any(lnk["match_status"] in ("auto_ambiguous_candidate", "unmatched") for lnk in links):
        status = "needs_review"
    else:
        status = "partial"

    await db.transactions_normalized.update_one(
        {"transaction_id": tx_id},
        {"$set": {"matching_status": status, "updated_at": now}}
    )

    return links_created
