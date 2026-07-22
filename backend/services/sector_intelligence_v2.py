"""Sector Intelligence V2 — CNAE-based dynamism engine.

Architecture:
- Computes scores per CNAE level (section, division, group)
- Multi-score: size_score, growth_score, activity_score → dynamism_score
- Sources: INE Demography, Procurement, BORME, Iberinform
- Multi-taxonomy ready: official_cnae (active), business_archetype (prepared)
- Designed for 3.3M companies scale

Weights:
  size_score    = f(active_companies, market_share)
  growth_score  = f(new_companies, yoy_change, dissolution_rate)
  activity_score = f(procurement_volume, borme_events, iberinform_signals)
  dynamism_score = 0.25 * size + 0.40 * growth + 0.35 * activity
"""

import logging
from typing import Dict, List, Optional
from database import db
from models import new_id, now_iso
from services.cnae_catalog import (
    CNAE_SECTIONS, CNAE_DIVISIONS, CNAE_GROUPS,
    cpv_to_cnae_division, get_section_for_division,
)

logger = logging.getLogger(__name__)

# Score combination weights
W_SIZE = 0.25
W_GROWTH = 0.40
W_ACTIVITY = 0.35

# Activity sub-weights (redistribute if source unavailable)
ACTIVITY_WEIGHTS = {"procurement": 0.40, "borme": 0.35, "iberinform": 0.25}

SIGNALS = {
    "sector_expansion": "Sector en expansión activa",
    "sector_contraction": "Sector en contracción",
    "emerging_sector": "Sector emergente con alto crecimiento",
    "mature_sector": "Sector maduro y estable",
    "high_public_demand": "Alta demanda pública (contratación)",
    "high_corporate_activity": "Alta actividad mercantil (BORME)",
    "stable_activity": "Actividad estable",
}


async def compute_sector_intelligence_v2() -> Dict:
    """Compute V2 sector intelligence across all CNAE levels."""
    now = now_iso()
    results = []

    # ── Gather raw data from all sources ──
    demography = await _gather_demography()
    procurement = await _gather_procurement()
    borme = await _gather_borme()
    iberinform = await _gather_iberinform()

    # ── Compute at Section level (A-U) ──
    for sec in CNAE_SECTIONS:
        code = sec["code"]
        div_codes = sec["divisions"]

        size = _aggregate_size(demography, div_codes, code)
        growth = _aggregate_growth(demography, div_codes, code)
        activity = _aggregate_activity(procurement, borme, iberinform, div_codes, code)

        sector = _build_sector_doc(
            cnae_code=code,
            cnae_level="section",
            cnae_label=sec["label"],
            size=size,
            growth=growth,
            activity=activity,
            now=now,
            taxonomy_type="official_cnae",
        )
        results.append(sector)

    # ── Compute at Division level (2-digit) ──
    for div_code, div_info in CNAE_DIVISIONS.items():
        size = _aggregate_size(demography, [div_code], div_code)
        growth = _aggregate_growth(demography, [div_code], div_code)
        activity = _aggregate_activity(procurement, borme, iberinform, [div_code], div_code)

        sector = _build_sector_doc(
            cnae_code=div_code,
            cnae_level="division",
            cnae_label=div_info["label"],
            size=size,
            growth=growth,
            activity=activity,
            now=now,
            taxonomy_type="official_cnae",
            parent_section=div_info["section"],
        )
        results.append(sector)

    # ── Compute at Group level (4-digit) ──
    for grp_code, grp_info in CNAE_GROUPS.items():
        div_code = grp_info["division"]
        section = get_section_for_division(div_code)

        size = _aggregate_size(demography, [grp_code], grp_code)
        growth = _aggregate_growth(demography, [grp_code], grp_code)
        activity = _aggregate_activity(procurement, borme, iberinform, [grp_code], grp_code)

        sector = _build_sector_doc(
            cnae_code=grp_code,
            cnae_level="group",
            cnae_label=grp_info["label"],
            size=size,
            growth=growth,
            activity=activity,
            now=now,
            taxonomy_type="official_cnae",
            parent_section=section,
            parent_division=div_code,
        )
        results.append(sector)

    # Sort by dynamism_score descending
    results.sort(key=lambda x: x["dynamism_score"], reverse=True)

    # ── Persist ──
    for sector in results:
        await db.sector_intelligence.update_one(
            {"cnae_code": sector["cnae_code"], "taxonomy_type": sector["taxonomy_type"]},
            {"$set": sector},
            upsert=True,
        )

    # Clean old CIS-based entries (PoC)
    await db.sector_intelligence.delete_many({"cnae_code": {"$exists": False}})

    return {
        "status": "completed",
        "version": "2.0",
        "taxonomy_type": "official_cnae",
        "sections": sum(1 for r in results if r["cnae_level"] == "section"),
        "divisions": sum(1 for r in results if r["cnae_level"] == "division"),
        "groups": sum(1 for r in results if r["cnae_level"] == "group"),
        "total": len(results),
        "generated_at": now,
    }


# ══════════════════════════════════════════
# DATA GATHERING
# ══════════════════════════════════════════

async def _gather_demography() -> Dict:
    """Gather business demography data from INE.
    
    Uses known DIRCE distribution to estimate per-CNAE company counts
    when we have the national total but not per-CNAE breakdowns.
    """
    from services.iberinform_processor import CNAE_DIVISION_DISTRIBUTION

    data = {
        "active_total": 0,
        "created_latest": 0,
        "dissolved_latest": 0,
        "yoy_change": 0,
        "by_division": {},
    }

    # National totals
    active = await db.business_demography.find_one(
        {"indicator_key": "companies_active", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )
    if active:
        data["active_total"] = active.get("value", 0) or 0

    created = await db.business_demography.find_one(
        {"indicator_key": "companies_created", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )
    if created:
        data["created_latest"] = created.get("value", 0) or 0
        data["yoy_change"] = created.get("yoy_change_pct", 0) or 0

    dissolved = await db.business_demography.find_one(
        {"indicator_key": "companies_dissolved", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )
    if dissolved:
        data["dissolved_latest"] = dissolved.get("value", 0) or 0

    # Use DIRCE distribution to estimate per-division company counts
    total = data["active_total"] or 3_300_000
    for div_code, share in CNAE_DIVISION_DISTRIBUTION.items():
        data["by_division"][div_code] = round(total * share)

    # Override with actual counts from iberinform_companies if higher
    ib_pipeline = [
        {"$group": {"_id": "$cnae_division", "count": {"$sum": 1}}},
    ]
    ib_by_cnae = await db.iberinform_companies.aggregate(ib_pipeline).to_list(200)
    for item in ib_by_cnae:
        code = str(item["_id"])
        if code in data["by_division"]:
            # Keep the DIRCE estimate (it's the national reality)
            # but record actual Iberinform count for enrichment signal
            pass

    return data


async def _gather_procurement() -> Dict:
    """Gather procurement data mapped to CNAE."""
    data = {"by_division": {}, "total_contracts": 0, "total_amount": 0}

    pipeline = [
        {"$group": {
            "_id": "$cpv_code",
            "count": {"$sum": 1},
            "amount": {"$sum": {"$ifNull": ["$amount", 0]}},
        }}
    ]
    by_cpv = await db.public_procurement_contracts.aggregate(pipeline).to_list(200)

    for item in by_cpv:
        cpv = item["_id"] or ""
        cnae_div = cpv_to_cnae_division(cpv)
        if cnae_div:
            if cnae_div not in data["by_division"]:
                data["by_division"][cnae_div] = {"count": 0, "amount": 0}
            data["by_division"][cnae_div]["count"] += item["count"]
            data["by_division"][cnae_div]["amount"] += item["amount"]
        data["total_contracts"] += item["count"]
        data["total_amount"] += item["amount"]

    return data


async def _gather_borme() -> Dict:
    """Gather BORME corporate events, ideally by CNAE."""
    data = {"by_division": {}, "total": 0}

    # Try CNAE-tagged events first
    pipeline_cnae = [
        {"$match": {"cnae_division": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$cnae_division", "count": {"$sum": 1}}},
    ]
    by_cnae = await db.borme_events.aggregate(pipeline_cnae).to_list(100)
    for item in by_cnae:
        data["by_division"][str(item["_id"])] = item["count"]

    # Total
    data["total"] = await db.borme_events.count_documents({})

    # If no CNAE-tagged events, use event_type distribution
    if not data["by_division"] and data["total"] > 0:
        type_pipeline = [
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        ]
        by_type = await db.borme_events.aggregate(type_pipeline).to_list(50)
        data["by_event_type"] = {item["_id"]: item["count"] for item in by_type}

    return data


async def _gather_iberinform() -> Dict:
    """Gather Iberinform company data by CNAE."""
    data = {"by_division": {}, "total": 0}

    pipeline = [
        {"$match": {"cnae_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"$substr": ["$cnae_code", 0, 2]},
            "count": {"$sum": 1},
            "avg_revenue": {"$avg": {"$ifNull": ["$revenue", 0]}},
        }},
    ]
    by_cnae = await db.iberinform_companies.aggregate(pipeline).to_list(100)
    for item in by_cnae:
        data["by_division"][item["_id"]] = {
            "count": item["count"],
            "avg_revenue": item.get("avg_revenue", 0),
        }
    data["total"] = sum(d["count"] for d in data["by_division"].values())

    return data


# ══════════════════════════════════════════
# SCORE COMPUTATION
# ══════════════════════════════════════════

def _aggregate_size(demography: Dict, div_codes: List[str], cnae_code: str) -> Dict:
    """Compute size_score based on company count and market share."""
    total_active = demography["active_total"] or 3_300_000  # Fallback to known Spanish total

    # Count companies in this CNAE scope
    companies = 0
    for dc in div_codes:
        companies += demography["by_division"].get(dc, 0)

    # If group-level (4-digit), check directly
    if len(cnae_code) == 4:
        companies = demography["by_division"].get(cnae_code, 0)

    market_share = companies / total_active if total_active > 0 else 0

    # Score: logarithmic scale — large sectors score higher but don't dominate
    if companies == 0:
        score = 0
    elif companies < 100:
        score = 10
    elif companies < 1000:
        score = 25
    elif companies < 10000:
        score = 45
    elif companies < 50000:
        score = 60
    elif companies < 200000:
        score = 75
    elif companies < 500000:
        score = 85
    else:
        score = 95

    return {
        "score": min(100, score),
        "active_companies": companies,
        "market_share": round(market_share, 6),
        "has_data": companies > 0,
    }


def _aggregate_growth(demography: Dict, div_codes: List[str], cnae_code: str) -> Dict:
    """Compute growth_score from company creation/dissolution dynamics."""
    national_created = demography["created_latest"] or 0
    national_dissolved = demography["dissolved_latest"] or 0
    national_yoy = demography["yoy_change"] or 0
    total_active = demography["active_total"] or 3_300_000

    # Per-CNAE company count to estimate proportional creation
    companies = 0
    for dc in div_codes:
        companies += demography["by_division"].get(dc, 0)
    if len(cnae_code) == 4:
        companies = demography["by_division"].get(cnae_code, 0)

    share = companies / total_active if total_active > 0 else 0

    # Estimate new/dissolved companies proportionally (until per-CNAE demography available)
    est_created = round(national_created * share) if national_created else 0
    est_dissolved = round(national_dissolved * share) if national_dissolved else 0
    net_balance = est_created - est_dissolved

    # Score based on national YoY and net balance
    if national_yoy > 10:
        base_score = 85
    elif national_yoy > 5:
        base_score = 70
    elif national_yoy > 2:
        base_score = 55
    elif national_yoy > 0:
        base_score = 45
    elif national_yoy > -2:
        base_score = 35
    elif national_yoy > -5:
        base_score = 25
    else:
        base_score = 10

    # Adjust for net balance direction
    if net_balance > 0:
        base_score = min(100, base_score + 5)
    elif net_balance < 0:
        base_score = max(0, base_score - 5)

    return {
        "score": min(100, max(0, base_score)),
        "estimated_new_companies": est_created,
        "estimated_dissolved": est_dissolved,
        "net_balance": net_balance,
        "national_yoy_pct": national_yoy,
        "has_data": national_created > 0,
    }


def _aggregate_activity(procurement: Dict, borme: Dict, iberinform: Dict,
                        div_codes: List[str], cnae_code: str) -> Dict:
    """Compute activity_score from procurement, BORME and Iberinform."""
    available_sources = []
    sub_scores = {}

    # ── Procurement ──
    proc_count = 0
    proc_amount = 0
    for dc in div_codes:
        p = procurement["by_division"].get(dc, {})
        if isinstance(p, dict):
            proc_count += p.get("count", 0)
            proc_amount += p.get("amount", 0)
    if len(cnae_code) == 4:
        # For groups, check if division has procurement
        div = cnae_code[:2]
        p = procurement["by_division"].get(div, {})
        if isinstance(p, dict):
            proc_count = p.get("count", 0)
            proc_amount = p.get("amount", 0)

    if proc_count > 0:
        import math
        # Logarithmic: 1 contract=30, 5=43, 10=50, 50=65, 100=72
        proc_score = min(100, 25 + 22 * math.log10(max(1, proc_count)) + min(30, proc_amount / 100000))
        sub_scores["procurement"] = round(proc_score)
        available_sources.append("procurement")

    # ── BORME ──
    borme_count = 0
    for dc in div_codes:
        borme_count += borme["by_division"].get(dc, 0)
    if len(cnae_code) == 4:
        borme_count = borme["by_division"].get(cnae_code[:2], 0)

    # If no CNAE-tagged BORME, distribute proportionally
    if borme_count == 0 and borme["total"] > 0:
        # Proportional estimate based on known company share
        total_known = sum(borme["by_division"].values()) if borme["by_division"] else 0
        if total_known == 0:
            # No CNAE tags at all — use event_type as proxy
            borme_count = 0  # Can't attribute without CNAE

    if borme_count > 0 or borme["total"] > 0:
        if borme_count > 0:
            # Logarithmic scale: differentiate between 10, 100, 500, 1000+ events
            import math
            borme_score = min(100, 20 + 18 * math.log10(max(1, borme_count)))
        else:
            borme_score = 15  # Baseline from national activity (no CNAE attribution)
        sub_scores["borme"] = round(borme_score)
        available_sources.append("borme")

    # ── Iberinform ──
    ib_count = 0
    for dc in div_codes:
        ib = iberinform["by_division"].get(dc, {})
        if isinstance(ib, dict):
            ib_count += ib.get("count", 0)
    if len(cnae_code) == 4:
        ib = iberinform["by_division"].get(cnae_code[:2], {})
        if isinstance(ib, dict):
            ib_count = ib.get("count", 0)

    if ib_count > 0:
        ib_score = min(100, 30 + ib_count * 2)
        sub_scores["iberinform"] = round(ib_score)
        available_sources.append("iberinform")

    # ── Combine with weight redistribution ──
    if not available_sources:
        combined = 0
    else:
        total_weight = sum(ACTIVITY_WEIGHTS[s] for s in available_sources)
        combined = 0
        for src in available_sources:
            adj_weight = ACTIVITY_WEIGHTS[src] / total_weight
            combined += sub_scores[src] * adj_weight
        combined = round(min(100, max(0, combined)))

    return {
        "score": combined,
        "sub_scores": sub_scores,
        "sources_available": available_sources,
        "partial_data": len(available_sources) < 3,
        "procurement_contracts": proc_count,
        "procurement_amount": round(proc_amount, 2),
        "borme_events": borme_count,
        "iberinform_companies": ib_count,
    }


def _build_sector_doc(
    cnae_code: str,
    cnae_level: str,
    cnae_label: str,
    size: Dict,
    growth: Dict,
    activity: Dict,
    now: str,
    taxonomy_type: str = "official_cnae",
    parent_section: str = None,
    parent_division: str = None,
) -> Dict:
    """Build the final sector intelligence document."""
    size_score = size["score"]
    growth_score = growth["score"]
    activity_score = activity["score"]

    dynamism_score = round(
        W_SIZE * size_score + W_GROWTH * growth_score + W_ACTIVITY * activity_score
    )
    dynamism_score = min(100, max(0, dynamism_score))

    # Trend
    if growth_score >= 60 and activity_score >= 50:
        trend = "up"
    elif growth_score <= 30 or activity_score <= 20:
        trend = "down"
    else:
        trend = "stable"

    # Signal
    signal = _compute_signal(dynamism_score, trend, size_score, growth_score, activity_score, activity)

    # Primary driver
    scores = {"size": size_score, "growth": growth_score, "activity": activity_score}
    primary_driver = max(scores, key=scores.get)

    # Source attribution
    all_sources = set()
    if growth["has_data"]:
        all_sources.add("INE Demografia Empresarial")
    if activity["procurement_contracts"] > 0:
        all_sources.add("Contratacion Publica")
    if activity["borme_events"] > 0:
        all_sources.add("BORME")
    if activity["iberinform_companies"] > 0:
        all_sources.add("Iberinform")
    if not all_sources:
        all_sources.add("INE Demografia Empresarial")

    partial = activity["partial_data"] or not size["has_data"]

    doc = {
        "cnae_code": cnae_code,
        "cnae_level": cnae_level,
        "cnae_label": cnae_label,
        "taxonomy_type": taxonomy_type,
        "size_score": size_score,
        "growth_score": growth_score,
        "activity_score": activity_score,
        "dynamism_score": dynamism_score,
        "trend_direction": trend,
        "signal": signal,
        "primary_driver": primary_driver,
        "active_companies": size["active_companies"],
        "market_share": size["market_share"],
        "new_companies_estimate": growth["estimated_new_companies"],
        "dissolved_estimate": growth["estimated_dissolved"],
        "net_balance": growth["net_balance"],
        "national_yoy_pct": growth["national_yoy_pct"],
        "procurement_contracts": activity["procurement_contracts"],
        "procurement_amount": activity["procurement_amount"],
        "borme_events": activity["borme_events"],
        "iberinform_companies": activity["iberinform_companies"],
        "activity_sub_scores": activity["sub_scores"],
        "sources_available": list(all_sources),
        "source_attribution": ", ".join(sorted(all_sources)),
        "partial_data": partial,
        "generated_at": now,
    }

    # Hierarchy references
    if parent_section:
        doc["parent_section"] = parent_section
    if parent_division:
        doc["parent_division"] = parent_division

    return doc


def _compute_signal(dynamism: int, trend: str, size: int, growth: int,
                    activity: int, activity_data: Dict) -> str:
    """Determine the most relevant signal for a sector."""
    if dynamism >= 70 and trend == "up":
        return "sector_expansion"
    if dynamism <= 25:
        return "sector_contraction"
    if growth >= 65 and dynamism >= 55:
        return "emerging_sector"
    if growth <= 30 and size >= 60:
        return "mature_sector"
    if activity_data.get("procurement_contracts", 0) >= 3:
        return "high_public_demand"
    if activity_data.get("borme_events", 0) >= 50:
        return "high_corporate_activity"
    return "stable_activity"
