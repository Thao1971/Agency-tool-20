"""Sector Intelligence — Computes dynamism scores and signals per sector.

Sources: INE Demography, Public Procurement, BORME, Companies Master.
Weights: INE 35%, Procurement 35%, BORME 20%, Iberinform 10%.
If source unavailable, redistribute weights and mark partial_data.
"""

import logging
from typing import Dict, List
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

# Map CPV codes to taxonomy categories
CPV_TO_CATEGORY = {
    "79341": "Creatividad y Produccion",
    "79342": "Digital, Growth y Commerce",
    "79340": "Creatividad y Produccion",
    "79416": "Comunicacion, PR y Reputacion",
    "79952": "Experiencias y Activacion (BTL)",
    "79950": "Experiencias y Activacion (BTL)",
    "79822": "Creatividad y Produccion",
    "72200": "Digital, Growth y Commerce",
    "72300": "Data, AdTech y MarTech",
    "79300": "Consultoria de Transformacion",
    "79310": "Consultoria de Transformacion",
    "79400": "Consultoria de Transformacion",
    "92110": "Creatividad y Produccion",
    "92111": "Creatividad y Produccion",
}

SIGNALS = {
    "sector_expansion": {"min_score": 70, "trend": "up"},
    "sector_contraction": {"max_score": 30, "trend": "down"},
    "emerging_sector": {"min_score": 60, "min_growth": 0.1},
    "mature_sector": {"max_growth": 0.02, "min_companies": 20},
    "public_demand_growth": {"min_procurement_growth": 0.1},
    "corporate_activity_growth": {"min_borme_growth": 0.1},
}

BASE_WEIGHTS = {"demography": 0.35, "procurement": 0.35, "borme": 0.20, "iberinform": 0.10}


async def compute_sector_intelligence() -> Dict:
    """Compute dynamism scores for all sectors."""
    now = now_iso()

    # Get all taxonomy categories
    categories = await db.taxonomy_categories.find({"active": True}, {"_id": 0}).sort("order", 1).to_list(20)

    # Gather data per source
    # 1. Companies master per category
    company_pipeline = [
        {"$match": {"category_name": {"$ne": None}}},
        {"$group": {"_id": "$category_name", "count": {"$sum": 1}}}
    ]
    companies_by_cat = {r["_id"]: r["count"] for r in await db.companies_master.aggregate(company_pipeline).to_list(20)}

    # 2. Procurement per category (via CPV mapping)
    proc_pipeline = [
        {"$group": {"_id": "$cpv_code", "count": {"$sum": 1}, "amount": {"$sum": {"$ifNull": ["$amount", 0]}}}}
    ]
    proc_by_cpv = await db.public_procurement_contracts.aggregate(proc_pipeline).to_list(50)
    procurement_by_cat = {}
    for p in proc_by_cpv:
        cpv = p["_id"] or ""
        for prefix, cat in CPV_TO_CATEGORY.items():
            if cpv.startswith(prefix):
                if cat not in procurement_by_cat:
                    procurement_by_cat[cat] = {"count": 0, "amount": 0}
                procurement_by_cat[cat]["count"] += p["count"]
                procurement_by_cat[cat]["amount"] += p["amount"]
                break

    # 3. BORME activity count (if events have category/sector info)
    borme_total = await db.borme_events.count_documents({})

    # 4. Business demography (national — distributed proportionally)
    latest_created = await db.business_demography.find_one(
        {"indicator_key": "companies_created"}, {"_id": 0}, sort=[("date", -1)]
    )
    national_created = latest_created.get("value", 0) if latest_created else 0
    national_yoy = latest_created.get("yoy_change_pct", 0) if latest_created else 0

    total_companies = sum(companies_by_cat.values()) or 1

    results = []
    for cat in categories:
        name = cat["name"]
        cat_id = cat["id"]

        # Company count
        n_companies = companies_by_cat.get(name, 0)
        company_share = n_companies / total_companies if total_companies > 0 else 0

        # Procurement
        proc = procurement_by_cat.get(name, {"count": 0, "amount": 0})

        # Estimated new companies (proportional to share)
        est_new = round(national_created * company_share) if national_created else 0

        # Compute sub-scores (0-100 each)
        available_sources = []
        sub_scores = {}

        # Demography sub-score
        if national_created > 0:
            demo_score = min(100, max(0, 50 + (national_yoy or 0) * 2))
            sub_scores["demography"] = demo_score
            available_sources.append("demography")

        # Procurement sub-score
        if proc["count"] > 0:
            proc_score = min(100, proc["count"] * 15 + (proc["amount"] / 100000) * 5)
            sub_scores["procurement"] = proc_score
            available_sources.append("procurement")

        # BORME sub-score (proportional activity)
        if borme_total > 0 and n_companies > 0:
            borme_share = n_companies / total_companies
            borme_score = min(100, 50 + borme_share * 200)
            sub_scores["borme"] = borme_score
            available_sources.append("borme")

        # Iberinform (not available yet — will use when processed)
        # sub_scores["iberinform"] = ...

        # Redistribute weights for available sources
        if not available_sources:
            dynamism_score = 0
        else:
            total_weight = sum(BASE_WEIGHTS[s] for s in available_sources)
            dynamism_score = 0
            for src in available_sources:
                adjusted_weight = BASE_WEIGHTS[src] / total_weight
                dynamism_score += sub_scores[src] * adjusted_weight
            dynamism_score = round(min(100, max(0, dynamism_score)))

        # Trend and signal
        trend = "up" if dynamism_score >= 60 else "down" if dynamism_score <= 35 else "stable"
        signal = _compute_signal(dynamism_score, trend, proc, national_yoy, n_companies)

        # Primary driver
        driver = None
        if proc["count"] > 0 and proc["amount"] > 50000:
            driver = "contratacion publica"
        elif national_yoy and national_yoy > 5:
            driver = "creacion empresarial"
        elif n_companies > 20:
            driver = "base empresarial solida"
        else:
            driver = "actividad general"

        sector = {
            "sector_id": cat_id,
            "sector_name": name,
            "period": latest_created.get("date", "")[:7] if latest_created else None,
            "active_companies": n_companies,
            "new_companies_estimate": est_new,
            "public_contracts_count": proc["count"],
            "public_contracts_amount": round(proc["amount"], 2),
            "borme_activity_count": round(borme_total * company_share) if borme_total else 0,
            "dynamism_score": dynamism_score,
            "trend_direction": trend,
            "signal": signal,
            "primary_driver": driver,
            "sub_scores": sub_scores,
            "sources_available": available_sources,
            "partial_data": len(available_sources) < 4,
            "generated_at": now,
        }
        results.append(sector)

    # Sort by dynamism_score desc
    results.sort(key=lambda x: x["dynamism_score"], reverse=True)

    # Persist
    for sector in results:
        await db.sector_intelligence.update_one(
            {"sector_id": sector["sector_id"], "period": sector["period"]},
            {"$set": sector},
            upsert=True
        )

    return {"status": "completed", "sectors": len(results), "generated_at": now}


def _compute_signal(score, trend, proc, national_yoy, n_companies):
    if score >= 70 and trend == "up":
        return "sector_expansion"
    if score <= 30:
        return "sector_contraction"
    if score >= 60 and (national_yoy or 0) > 10:
        return "emerging_sector"
    if (national_yoy or 0) < 2 and n_companies > 20:
        return "mature_sector"
    if proc["count"] > 3:
        return "public_demand_growth"
    return "stable_activity"
