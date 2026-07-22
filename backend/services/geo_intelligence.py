"""Geo Intelligence — Territorial dynamism engine.

Computes scores per geographic level (CCAA, Province).
Multi-score: size_score, growth_score, activity_score → dynamism_score.
Sources: INE Demography, BORME (registry_province), Procurement, Iberinform.

Weights (same pattern as Sector Intelligence V2):
  dynamism_score = 0.25 * size + 0.40 * growth + 0.35 * activity
"""

import logging
import math
from typing import Dict, List
from database import db
from models import now_iso
from services.geo_catalog import (
    CCAA, PROVINCES,
    resolve_borme_province, get_ccaa_for_province,
    get_ccaa_label, get_province_label,
)

logger = logging.getLogger(__name__)

W_SIZE = 0.25
W_GROWTH = 0.40
W_ACTIVITY = 0.35

ACTIVITY_WEIGHTS = {"borme": 0.45, "procurement": 0.35, "iberinform": 0.20}

SIGNALS = {
    "territory_expansion": "Territorio en expansión activa",
    "territory_contraction": "Territorio en contracción",
    "high_creation": "Alta creación empresarial",
    "high_dissolution": "Alta tasa de disoluciones",
    "public_investment_hub": "Polo de inversión pública",
    "corporate_hub": "Hub de actividad corporativa",
    "stable_territory": "Territorio estable",
}


async def compute_geo_intelligence() -> Dict:
    """Compute geo intelligence for all CCAA and Provinces."""
    now = now_iso()
    results = []

    # Gather raw data
    demography = await _gather_demography()
    borme = await _gather_borme()
    procurement = await _gather_procurement()
    iberinform = await _gather_iberinform()

    # ── Compute at Province level ──
    province_data = {}
    for prov_code, prov_info in PROVINCES.items():
        prov_label = prov_info["label"]
        ccaa_code = prov_info["ccaa"]

        size = _compute_size(demography, prov_code, "province")
        growth = _compute_growth(demography, prov_code, "province")
        activity = _compute_activity(borme, procurement, iberinform, prov_code, "province")

        doc = _build_geo_doc(
            geo_id=prov_code,
            geo_level="province",
            geo_name=prov_label,
            parent_ccaa=ccaa_code,
            size=size,
            growth=growth,
            activity=activity,
            now=now,
        )
        results.append(doc)
        province_data[prov_code] = doc

    # ── Compute at CCAA level (aggregate from provinces) ──
    for ccaa in CCAA:
        ccaa_code = ccaa["code"]
        ccaa_label = ccaa["label"]
        prov_codes = ccaa["provinces"]

        size = _compute_size_ccaa(demography, province_data, prov_codes)
        growth = _compute_growth_ccaa(demography, province_data, prov_codes)
        activity = _compute_activity_ccaa(borme, procurement, iberinform, prov_codes)

        doc = _build_geo_doc(
            geo_id=ccaa_code,
            geo_level="ccaa",
            geo_name=ccaa_label,
            parent_ccaa=None,
            size=size,
            growth=growth,
            activity=activity,
            now=now,
        )
        results.append(doc)

    # Sort by dynamism descending
    results.sort(key=lambda x: x["dynamism_score"], reverse=True)

    # Persist
    for doc in results:
        await db.geo_intelligence.update_one(
            {"geo_id": doc["geo_id"], "geo_level": doc["geo_level"]},
            {"$set": doc},
            upsert=True,
        )

    ccaa_count = sum(1 for r in results if r["geo_level"] == "ccaa")
    prov_count = sum(1 for r in results if r["geo_level"] == "province")

    return {
        "status": "completed",
        "version": "1.0",
        "ccaa": ccaa_count,
        "provinces": prov_count,
        "total": len(results),
        "generated_at": now,
    }


# ══════════════════════════════════════════
# DATA GATHERING
# ══════════════════════════════════════════

async def _gather_demography() -> Dict:
    """National-level demography data. Per-province when available."""
    data = {
        "active_total": 0,
        "created_latest": 0,
        "dissolved_latest": 0,
        "yoy_change": 0,
        "by_province": {},
    }

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

    # Per-province: use known DIRCE distribution for real estimates
    from services.iberinform_processor import PROVINCE_DISTRIBUTION
    total = data["active_total"] or 3_300_000
    for prov_code, share in PROVINCE_DISTRIBUTION.items():
        data["by_province"][prov_code] = round(total * share)

    return data


async def _gather_borme() -> Dict:
    """BORME events by registry_province."""
    data = {"by_province": {}, "total": 0}

    pipeline = [
        {"$match": {"registry_province": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$registry_province", "count": {"$sum": 1}}},
    ]
    by_reg = await db.borme_events.aggregate(pipeline).to_list(60)

    for item in by_reg:
        prov_code = resolve_borme_province(item["_id"])
        if prov_code:
            data["by_province"][prov_code] = data["by_province"].get(prov_code, 0) + item["count"]

    data["total"] = await db.borme_events.count_documents({})
    return data


async def _gather_procurement() -> Dict:
    """Procurement by province (if geographic data available)."""
    data = {"by_province": {}, "total_contracts": 0, "total_amount": 0}

    # Try province-tagged contracts
    pipeline = [
        {"$match": {"province_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": "$province_code",
            "count": {"$sum": 1},
            "amount": {"$sum": {"$ifNull": ["$amount", 0]}},
        }},
    ]
    by_prov = await db.public_procurement_contracts.aggregate(pipeline).to_list(60)
    for item in by_prov:
        data["by_province"][str(item["_id"])] = {
            "count": item["count"],
            "amount": item["amount"],
        }

    total = await db.public_procurement_contracts.aggregate([
        {"$group": {"_id": None, "count": {"$sum": 1}, "amount": {"$sum": {"$ifNull": ["$amount", 0]}}}}
    ]).to_list(1)
    if total:
        data["total_contracts"] = total[0]["count"]
        data["total_amount"] = total[0]["amount"]

    return data


async def _gather_iberinform() -> Dict:
    """Iberinform company data by province."""
    data = {"by_province": {}, "total": 0}

    pipeline = [
        {"$match": {"province_code": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": "$province_code",
            "count": {"$sum": 1},
            "avg_revenue": {"$avg": {"$ifNull": ["$revenue", 0]}},
        }},
    ]
    by_prov = await db.iberinform_companies.aggregate(pipeline).to_list(60)
    for item in by_prov:
        data["by_province"][str(item["_id"])] = {
            "count": item["count"],
            "avg_revenue": item.get("avg_revenue", 0),
        }
    data["total"] = sum(d["count"] for d in data["by_province"].values())
    return data


# ══════════════════════════════════════════
# PROVINCE-LEVEL SCORE COMPUTATION
# ══════════════════════════════════════════

# Known approximate distribution of active companies by province (INE DIRCE 2025)
# Source: INE, Directorio Central de Empresas. Top provinces by company count.
PROVINCE_COMPANY_SHARE = {
    "28": 0.162, "08": 0.130, "46": 0.062, "41": 0.042, "29": 0.041,
    "03": 0.040, "30": 0.027, "07": 0.027, "50": 0.024, "48": 0.024,
    "33": 0.020, "35": 0.020, "38": 0.019, "17": 0.018, "43": 0.017,
    "11": 0.016, "15": 0.016, "36": 0.016, "18": 0.015, "20": 0.014,
    "47": 0.012, "21": 0.010, "23": 0.009, "14": 0.013, "04": 0.012,
    "45": 0.012, "12": 0.011, "39": 0.010, "31": 0.013, "01": 0.008,
    "06": 0.009, "37": 0.007, "24": 0.007, "10": 0.007, "27": 0.005,
    "09": 0.007, "19": 0.004, "16": 0.004, "22": 0.005, "34": 0.003,
    "44": 0.003, "32": 0.005, "26": 0.007, "40": 0.003, "02": 0.007,
    "13": 0.008, "25": 0.008, "05": 0.003, "42": 0.002, "49": 0.003,
    "51": 0.001, "52": 0.001,
}


def _compute_size(demography: Dict, prov_code: str, level: str) -> Dict:
    """Size score for a province."""
    total_active = demography["active_total"] or 3_300_000

    # Use DIRCE-estimated count from demography
    est_companies = demography["by_province"].get(prov_code, 0)
    share = est_companies / total_active if total_active > 0 else 0

    # Logarithmic scoring
    if est_companies == 0:
        score = 0
    elif est_companies < 5000:
        score = 15
    elif est_companies < 20000:
        score = 30
    elif est_companies < 50000:
        score = 45
    elif est_companies < 100000:
        score = 60
    elif est_companies < 250000:
        score = 75
    elif est_companies < 500000:
        score = 88
    else:
        score = 95

    return {
        "score": min(100, score),
        "active_companies": est_companies,
        "market_share": round(share, 6),
        "has_data": True,
    }


def _compute_growth(demography: Dict, prov_code: str, level: str) -> Dict:
    """Growth score for a province."""
    national_created = demography["created_latest"] or 0
    national_dissolved = demography["dissolved_latest"] or 0
    national_yoy = demography["yoy_change"] or 0
    total_active = demography["active_total"] or 3_300_000

    est_companies = demography["by_province"].get(prov_code, 0)
    share = est_companies / total_active if total_active > 0 else 0
    est_created = round(national_created * share)
    est_dissolved = round(national_dissolved * share)
    net = est_created - est_dissolved

    # Base score from national YoY
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

    # Adjust for net balance
    if net > 0:
        base_score = min(100, base_score + 5)
    elif net < 0:
        base_score = max(0, base_score - 5)

    return {
        "score": min(100, max(0, base_score)),
        "new_companies": est_created,
        "closed_companies": est_dissolved,
        "net_company_creation": net,
        "national_yoy_pct": national_yoy,
        "has_data": national_created > 0,
    }


def _compute_activity(borme: Dict, procurement: Dict, iberinform: Dict,
                      prov_code: str, level: str) -> Dict:
    """Activity score for a province from BORME, procurement, Iberinform."""
    available_sources = []
    sub_scores = {}

    # BORME
    borme_count = borme["by_province"].get(prov_code, 0)
    if borme_count > 0:
        borme_score = min(100, 20 + 18 * math.log10(max(1, borme_count)))
        sub_scores["borme"] = round(borme_score)
        available_sources.append("borme")

    # Procurement
    proc = procurement["by_province"].get(prov_code, {})
    proc_count = proc.get("count", 0) if isinstance(proc, dict) else 0
    proc_amount = proc.get("amount", 0) if isinstance(proc, dict) else 0
    if proc_count > 0:
        proc_score = min(100, 25 + 22 * math.log10(max(1, proc_count)) + min(30, proc_amount / 100000))
        sub_scores["procurement"] = round(proc_score)
        available_sources.append("procurement")

    # Iberinform
    ib = iberinform["by_province"].get(prov_code, {})
    ib_count = ib.get("count", 0) if isinstance(ib, dict) else 0
    if ib_count > 0:
        ib_score = min(100, 30 + ib_count * 2)
        sub_scores["iberinform"] = round(ib_score)
        available_sources.append("iberinform")

    # Combine
    if not available_sources:
        combined = 0
    else:
        total_weight = sum(ACTIVITY_WEIGHTS[s] for s in available_sources)
        combined = 0
        for src in available_sources:
            adj = ACTIVITY_WEIGHTS[src] / total_weight
            combined += sub_scores[src] * adj
        combined = round(min(100, max(0, combined)))

    return {
        "score": combined,
        "sub_scores": sub_scores,
        "sources_available": available_sources,
        "partial_data": len(available_sources) < 3,
        "borme_activity_count": borme_count,
        "public_contracts_count": proc_count,
        "public_contracts_amount": round(proc_amount, 2),
        "iberinform_companies": ib_count,
    }


# ══════════════════════════════════════════
# CCAA-LEVEL AGGREGATION
# ══════════════════════════════════════════

def _compute_size_ccaa(demography: Dict, province_data: Dict, prov_codes: List[str]) -> Dict:
    """Aggregate size from provinces."""
    total_companies = sum(
        province_data.get(pc, {}).get("active_companies", 0) for pc in prov_codes
    )
    total_active = demography["active_total"] or 3_300_000
    share = total_companies / total_active if total_active > 0 else 0

    if total_companies == 0:
        score = 0
    elif total_companies < 20000:
        score = 15
    elif total_companies < 50000:
        score = 30
    elif total_companies < 100000:
        score = 45
    elif total_companies < 200000:
        score = 58
    elif total_companies < 400000:
        score = 72
    elif total_companies < 600000:
        score = 85
    else:
        score = 95

    return {
        "score": min(100, score),
        "active_companies": total_companies,
        "market_share": round(share, 6),
        "has_data": True,
    }


def _compute_growth_ccaa(demography: Dict, province_data: Dict, prov_codes: List[str]) -> Dict:
    """Aggregate growth from provinces."""
    total_new = sum(
        province_data.get(pc, {}).get("new_companies", 0) for pc in prov_codes
    )
    total_closed = sum(
        province_data.get(pc, {}).get("closed_companies", 0) for pc in prov_codes
    )
    net = total_new - total_closed
    national_yoy = demography["yoy_change"] or 0

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

    if net > 0:
        base_score = min(100, base_score + 5)
    elif net < 0:
        base_score = max(0, base_score - 5)

    return {
        "score": min(100, max(0, base_score)),
        "new_companies": total_new,
        "closed_companies": total_closed,
        "net_company_creation": net,
        "national_yoy_pct": national_yoy,
        "has_data": demography["created_latest"] > 0,
    }


def _compute_activity_ccaa(borme: Dict, procurement: Dict, iberinform: Dict,
                           prov_codes: List[str]) -> Dict:
    """Aggregate activity from provinces for a CCAA."""
    available_sources = []
    sub_scores = {}

    # Sum BORME across provinces
    borme_count = sum(borme["by_province"].get(pc, 0) for pc in prov_codes)
    if borme_count > 0:
        borme_score = min(100, 20 + 18 * math.log10(max(1, borme_count)))
        sub_scores["borme"] = round(borme_score)
        available_sources.append("borme")

    # Sum procurement
    proc_count = 0
    proc_amount = 0
    for pc in prov_codes:
        p = procurement["by_province"].get(pc, {})
        if isinstance(p, dict):
            proc_count += p.get("count", 0)
            proc_amount += p.get("amount", 0)
    if proc_count > 0:
        proc_score = min(100, 25 + 22 * math.log10(max(1, proc_count)) + min(30, proc_amount / 100000))
        sub_scores["procurement"] = round(proc_score)
        available_sources.append("procurement")

    # Sum Iberinform
    ib_count = 0
    for pc in prov_codes:
        ib = iberinform["by_province"].get(pc, {})
        if isinstance(ib, dict):
            ib_count += ib.get("count", 0)
    if ib_count > 0:
        ib_score = min(100, 30 + ib_count * 2)
        sub_scores["iberinform"] = round(ib_score)
        available_sources.append("iberinform")

    if not available_sources:
        combined = 0
    else:
        total_weight = sum(ACTIVITY_WEIGHTS[s] for s in available_sources)
        combined = 0
        for src in available_sources:
            adj = ACTIVITY_WEIGHTS[src] / total_weight
            combined += sub_scores[src] * adj
        combined = round(min(100, max(0, combined)))

    return {
        "score": combined,
        "sub_scores": sub_scores,
        "sources_available": available_sources,
        "partial_data": len(available_sources) < 3,
        "borme_activity_count": borme_count,
        "public_contracts_count": proc_count,
        "public_contracts_amount": round(proc_amount, 2),
        "iberinform_companies": ib_count,
    }


# ══════════════════════════════════════════
# DOCUMENT BUILDER
# ══════════════════════════════════════════

def _build_geo_doc(geo_id: str, geo_level: str, geo_name: str, parent_ccaa: str | None,
                   size: Dict, growth: Dict, activity: Dict, now: str) -> Dict:
    """Build the final geo intelligence document."""
    size_score = size["score"]
    growth_score = growth["score"]
    activity_score = activity["score"]

    dynamism_score = round(
        W_SIZE * size_score + W_GROWTH * growth_score + W_ACTIVITY * activity_score
    )
    dynamism_score = min(100, max(0, dynamism_score))

    if growth_score >= 60 and activity_score >= 50:
        trend = "up"
    elif growth_score <= 30 or activity_score <= 20:
        trend = "down"
    else:
        trend = "stable"

    signal = _compute_signal(dynamism_score, trend, size_score, growth_score, activity_score, activity)

    scores = {"size": size_score, "growth": growth_score, "activity": activity_score}
    primary_driver = max(scores, key=scores.get)

    all_sources = set()
    if growth["has_data"]:
        all_sources.add("INE Demografia Empresarial")
    if activity["borme_activity_count"] > 0:
        all_sources.add("BORME")
    if activity["public_contracts_count"] > 0:
        all_sources.add("Contratacion Publica")
    if activity["iberinform_companies"] > 0:
        all_sources.add("Iberinform")
    if not all_sources:
        all_sources.add("INE Demografia Empresarial")

    doc = {
        "geo_id": geo_id,
        "geo_level": geo_level,
        "geo_name": geo_name,
        "period": None,
        "active_companies": size["active_companies"],
        "new_companies": growth["new_companies"],
        "closed_companies": growth["closed_companies"],
        "net_company_creation": growth["net_company_creation"],
        "public_contracts_count": activity["public_contracts_count"],
        "public_contracts_amount": activity["public_contracts_amount"],
        "borme_activity_count": activity["borme_activity_count"],
        "revenue_growth": None,
        "ebitda_growth": None,
        "employment_growth": None,
        "size_score": size_score,
        "growth_score": growth_score,
        "activity_score": activity_score,
        "dynamism_score": dynamism_score,
        "trend_direction": trend,
        "signal": signal,
        "primary_driver": primary_driver,
        "activity_sub_scores": activity["sub_scores"],
        "sources_available": list(all_sources),
        "source_attribution": ", ".join(sorted(all_sources)),
        "partial_data": activity["partial_data"],
        "generated_at": now,
    }

    if parent_ccaa:
        doc["parent_ccaa"] = parent_ccaa

    return doc


def _compute_signal(dynamism: int, trend: str, size: int, growth: int,
                    activity: int, activity_data: Dict) -> str:
    if dynamism >= 70 and trend == "up":
        return "territory_expansion"
    if dynamism <= 25:
        return "territory_contraction"
    if growth >= 65 and dynamism >= 55:
        return "high_creation"
    if activity_data.get("public_contracts_count", 0) >= 5:
        return "public_investment_hub"
    if activity_data.get("borme_activity_count", 0) >= 500:
        return "corporate_hub"
    return "stable_territory"
