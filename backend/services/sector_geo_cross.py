"""Sector × Geo Cross-Intelligence — What sectors grow where.

Crosses CNAE sector data with geographic territory data to answer:
- What sectors grow most in Madrid?
- Where does tech (J) concentrate?
- Which province leads in Construction?

Sources: BORME (cnae_division + registry_province), Iberinform (cnae + province),
         DIRCE distribution for baseline estimates.
"""

import logging
import math
from typing import Dict, List
from database import db
from models import now_iso
from services.cnae_catalog import CNAE_SECTIONS, CNAE_DIVISIONS, get_section_for_division
from services.geo_catalog import (
    CCAA, PROVINCES, resolve_borme_province, get_ccaa_for_province,
    get_ccaa_label, get_province_label,
)
from services.iberinform_processor import CNAE_DIVISION_DISTRIBUTION, PROVINCE_DISTRIBUTION

logger = logging.getLogger(__name__)


async def compute_sector_geo_cross() -> Dict:
    """Compute crossed sector × geo intelligence."""
    now = now_iso()

    # Gather crossed data
    borme_cross = await _gather_borme_cross()
    ib_cross = await _gather_iberinform_cross()

    # Get national totals
    active_doc = await db.business_demography.find_one(
        {"indicator_key": "companies_active", "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )
    national_total = (active_doc.get("value", 0) if active_doc else 0) or 3_300_000

    results = []

    # Compute for each CNAE section × province combination
    for sec in CNAE_SECTIONS:
        sec_code = sec["code"]
        div_codes = sec["divisions"]

        for prov_code, prov_info in PROVINCES.items():
            ccaa_code = prov_info["ccaa"]

            # Estimate company count from DIRCE distributions
            cnae_share = sum(CNAE_DIVISION_DISTRIBUTION.get(d, 0) for d in div_codes)
            prov_share = PROVINCE_DISTRIBUTION.get(prov_code, 0.001)
            est_companies = round(national_total * cnae_share * prov_share)

            # BORME activity for this cross
            borme_count = 0
            for dc in div_codes:
                borme_count += borme_cross.get((dc, prov_code), 0)

            # Iberinform companies
            ib_count = 0
            for dc in div_codes:
                ib_count += ib_cross.get((dc, prov_code), 0)

            # Skip empty combinations
            if est_companies == 0 and borme_count == 0 and ib_count == 0:
                continue

            # Concentration index: how much this sector is over/under-represented here
            expected_share = cnae_share * prov_share
            if borme_count > 0 and sum(borme_cross.values()) > 0:
                actual_share = borme_count / sum(borme_cross.values())
                concentration = round(actual_share / expected_share, 2) if expected_share > 0 else 0
            else:
                concentration = 1.0

            # Activity score (0-100)
            activity = 0
            if borme_count > 0:
                activity = min(100, round(20 + 18 * math.log10(max(1, borme_count))))

            doc = {
                "cnae_section": sec_code,
                "cnae_label": sec["label"],
                "province_code": prov_code,
                "province_name": prov_info["label"],
                "ccaa_code": ccaa_code,
                "estimated_companies": est_companies,
                "borme_events": borme_count,
                "iberinform_companies": ib_count,
                "concentration_index": concentration,
                "activity_score": activity,
                "generated_at": now,
            }
            results.append(doc)

    # Persist
    await db.sector_geo_cross.delete_many({})
    if results:
        await db.sector_geo_cross.insert_many(results)

    return {
        "status": "completed",
        "combinations": len(results),
        "generated_at": now,
    }


async def _gather_borme_cross() -> Dict:
    """BORME events by (cnae_division, province_code)."""
    pipeline = [
        {"$match": {"cnae_division": {"$ne": None}, "registry_province": {"$nin": [None, ""]}}},
        {"$group": {"_id": {"cnae": "$cnae_division", "prov": "$registry_province"}, "count": {"$sum": 1}}},
    ]
    raw = await db.borme_events.aggregate(pipeline).to_list(5000)

    result = {}
    for item in raw:
        cnae = item["_id"]["cnae"]
        prov_name = item["_id"]["prov"]
        prov_code = resolve_borme_province(prov_name)
        if prov_code:
            result[(cnae, prov_code)] = result.get((cnae, prov_code), 0) + item["count"]
    return result


async def _gather_iberinform_cross() -> Dict:
    """Iberinform companies by (cnae_division, province_code)."""
    pipeline = [
        {"$match": {"cnae_division": {"$ne": None}, "province_code": {"$ne": None}}},
        {"$group": {"_id": {"cnae": "$cnae_division", "prov": "$province_code"}, "count": {"$sum": 1}}},
    ]
    raw = await db.iberinform_companies.aggregate(pipeline).to_list(5000)

    result = {}
    for item in raw:
        result[(item["_id"]["cnae"], item["_id"]["prov"])] = item["count"]
    return result


# ══════════════════════════════════════════
# QUERY HELPERS (for routes)
# ══════════════════════════════════════════

async def get_sectors_in_territory(geo_level: str, geo_code: str, limit: int = 21) -> List[Dict]:
    """What sectors are most active in a territory? (e.g., sectors in Madrid)"""
    if geo_level == "province":
        match = {"province_code": geo_code}
    else:
        match = {"ccaa_code": geo_code}

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"section": "$cnae_section", "label": "$cnae_label"},
            "estimated_companies": {"$sum": "$estimated_companies"},
            "borme_events": {"$sum": "$borme_events"},
            "iberinform_companies": {"$sum": "$iberinform_companies"},
            "avg_concentration": {"$avg": "$concentration_index"},
            "max_activity": {"$max": "$activity_score"},
        }},
        {"$sort": {"borme_events": -1}},
        {"$limit": limit},
    ]
    rows = await db.sector_geo_cross.aggregate(pipeline).to_list(limit)

    return [{
        "cnae_section": r["_id"]["section"],
        "cnae_label": r["_id"]["label"],
        "estimated_companies": r["estimated_companies"],
        "borme_events": r["borme_events"],
        "iberinform_companies": r["iberinform_companies"],
        "concentration_index": round(r["avg_concentration"], 2),
        "activity_score": r["max_activity"],
    } for r in rows]


async def get_territories_for_sector(cnae_section: str, geo_level: str = "province",
                                     limit: int = 20) -> List[Dict]:
    """Where does a sector concentrate? (e.g., where is tech strongest?)"""
    if geo_level == "ccaa":
        pipeline = [
            {"$match": {"cnae_section": cnae_section}},
            {"$group": {
                "_id": {"ccaa": "$ccaa_code"},
                "estimated_companies": {"$sum": "$estimated_companies"},
                "borme_events": {"$sum": "$borme_events"},
                "iberinform_companies": {"$sum": "$iberinform_companies"},
                "avg_concentration": {"$avg": "$concentration_index"},
                "max_activity": {"$max": "$activity_score"},
            }},
            {"$sort": {"borme_events": -1}},
            {"$limit": limit},
        ]
        rows = await db.sector_geo_cross.aggregate(pipeline).to_list(limit)
        return [{
            "geo_id": r["_id"]["ccaa"],
            "geo_name": get_ccaa_label(r["_id"]["ccaa"]) or r["_id"]["ccaa"],
            "geo_level": "ccaa",
            "estimated_companies": r["estimated_companies"],
            "borme_events": r["borme_events"],
            "iberinform_companies": r["iberinform_companies"],
            "concentration_index": round(r["avg_concentration"], 2),
            "activity_score": r["max_activity"],
        } for r in rows]
    else:
        pipeline = [
            {"$match": {"cnae_section": cnae_section}},
            {"$sort": {"borme_events": -1}},
            {"$limit": limit},
        ]
        rows = await db.sector_geo_cross.aggregate(pipeline).to_list(limit)
        return [{
            "geo_id": r["province_code"],
            "geo_name": r["province_name"],
            "geo_level": "province",
            "estimated_companies": r["estimated_companies"],
            "borme_events": r["borme_events"],
            "iberinform_companies": r["iberinform_companies"],
            "concentration_index": r["concentration_index"],
            "activity_score": r["activity_score"],
        } for r in rows]


async def get_heatmap_data(cnae_section: str = None) -> List[Dict]:
    """Get data for a sector × territory heatmap."""
    match = {}
    if cnae_section:
        match["cnae_section"] = cnae_section

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {
            "_id": {"section": "$cnae_section", "ccaa": "$ccaa_code"},
            "borme_events": {"$sum": "$borme_events"},
            "estimated_companies": {"$sum": "$estimated_companies"},
            "max_activity": {"$max": "$activity_score"},
        }},
        {"$sort": {"borme_events": -1}},
    ]
    rows = await db.sector_geo_cross.aggregate(pipeline).to_list(500)

    return [{
        "cnae_section": r["_id"]["section"],
        "ccaa_code": r["_id"]["ccaa"],
        "ccaa_name": get_ccaa_label(r["_id"]["ccaa"]) or r["_id"]["ccaa"],
        "borme_events": r["borme_events"],
        "estimated_companies": r["estimated_companies"],
        "activity_score": r["max_activity"],
    } for r in rows]
