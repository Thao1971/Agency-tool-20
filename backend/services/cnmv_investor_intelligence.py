"""CNMV Investor Intelligence — Maps financial buyers to sectors with confidence tracking.

Every data point has:
  - confidence_level: A (official CNMV), B (inferred), C (validated manually)
  - confidence_score: 0-100
  - source_type: cnmv | internal_ai | manual_review
  - confidence_reason: human-readable explanation
  - data_lineage: {field: source} map
"""

import re
from typing import Dict, List
from database import db
from models import new_id, now_iso
from services.cnmv_catalog import CNMV_ENTITY_CATALOG

# Keywords in fund/manager names → CNAE sector mapping with confidence
SECTOR_KEYWORDS = {
    # Technology / Digital (high confidence — very specific terms)
    "tech": {"cnaes": ["62", "63"], "score": 82},
    "digital": {"cnaes": ["62", "63"], "score": 75},
    "software": {"cnaes": ["62"], "score": 90},
    "fintech": {"cnaes": ["64", "66"], "score": 88},
    "biotech": {"cnaes": ["21", "72"], "score": 90},
    "deeptech": {"cnaes": ["72"], "score": 85},
    "cyber": {"cnaes": ["62"], "score": 88},
    "cloud": {"cnaes": ["62", "63"], "score": 82},
    "ai": {"cnaes": ["62"], "score": 80},
    "data": {"cnaes": ["62", "63"], "score": 70},
    # Real Estate / Infrastructure
    "inmobili": {"cnaes": ["68"], "score": 95},
    "real estate": {"cnaes": ["68"], "score": 95},
    "property": {"cnaes": ["68"], "score": 90},
    "solar": {"cnaes": ["35"], "score": 92},
    "energy": {"cnaes": ["35"], "score": 85},
    "renovable": {"cnaes": ["35"], "score": 90},
    "renewable": {"cnaes": ["35"], "score": 90},
    "infraestruc": {"cnaes": ["42"], "score": 88},
    "infrastructure": {"cnaes": ["42"], "score": 88},
    # Healthcare / Pharma
    "health": {"cnaes": ["86"], "score": 85},
    "salud": {"cnaes": ["86"], "score": 88},
    "pharma": {"cnaes": ["21"], "score": 92},
    "farma": {"cnaes": ["21"], "score": 92},
    "biomedic": {"cnaes": ["21", "86"], "score": 88},
    "life science": {"cnaes": ["21", "72"], "score": 90},
    "medic": {"cnaes": ["86"], "score": 80},
    "clinic": {"cnaes": ["86"], "score": 82},
    # Food / Agriculture
    "agro": {"cnaes": ["01"], "score": 88},
    "agri": {"cnaes": ["01"], "score": 88},
    "food": {"cnaes": ["10"], "score": 85},
    "alimenta": {"cnaes": ["10"], "score": 90},
    "wine": {"cnaes": ["11"], "score": 92},
    "vino": {"cnaes": ["11"], "score": 92},
    # Industry / Manufacturing
    "industrial": {"cnaes": ["25", "28"], "score": 78},
    "manufactur": {"cnaes": ["25"], "score": 80},
    "automotiv": {"cnaes": ["29"], "score": 90},
    "aero": {"cnaes": ["30", "51"], "score": 88},
    "naval": {"cnaes": ["30"], "score": 90},
    # Services / Consulting
    "consulting": {"cnaes": ["70"], "score": 78},
    "consultori": {"cnaes": ["70"], "score": 80},
    "education": {"cnaes": ["85"], "score": 85},
    "educaci": {"cnaes": ["85"], "score": 88},
    "travel": {"cnaes": ["79"], "score": 85},
    "turismo": {"cnaes": ["79"], "score": 88},
    "hotel": {"cnaes": ["55"], "score": 90},
    # Media / Entertainment
    "media": {"cnaes": ["60"], "score": 72},
    "audiovisual": {"cnaes": ["59"], "score": 85},
    "entertainment": {"cnaes": ["93"], "score": 80},
    "gaming": {"cnaes": ["58"], "score": 85},
    "contenido": {"cnaes": ["59"], "score": 78},
    # Retail / Consumer
    "retail": {"cnaes": ["47"], "score": 85},
    "consumer": {"cnaes": ["47"], "score": 75},
    "ecommerce": {"cnaes": ["47"], "score": 82},
    "moda": {"cnaes": ["14"], "score": 90},
    "fashion": {"cnaes": ["14"], "score": 90},
    "luxury": {"cnaes": ["14"], "score": 82},
    # Financial
    "credit": {"cnaes": ["64"], "score": 80},
    "lending": {"cnaes": ["64"], "score": 82},
    "insurance": {"cnaes": ["65"], "score": 88},
    "asset": {"cnaes": ["66"], "score": 70},
    "wealth": {"cnaes": ["66"], "score": 78},
    "pension": {"cnaes": ["65"], "score": 85},
}

BUYER_TYPES = {"scr", "fcr", "scr_pyme", "fcr_pyme", "fcr_europeo",
               "ficc", "sicc", "fese", "filpe"}
MANAGER_TYPES = {"sgeic", "sgiic", "esi", "eaf", "eafn"}


async def build_investor_sector_map() -> Dict:
    """Analyze all entities and map to CNAE with confidence scores."""
    now = now_iso()
    mapped = 0
    total = 0

    entities = await db.cnmv_entities.find(
        {}, {"_id": 0, "nif": 1, "name": 1, "entity_type": 1}
    ).to_list(5000)

    for e in entities:
        total += 1
        name_lower = e["name"].lower()
        sector_matches = []

        for keyword, config in SECTOR_KEYWORDS.items():
            if keyword in name_lower and config["cnaes"]:
                for cnae in config["cnaes"]:
                    sector_matches.append({
                        "cnae": cnae,
                        "keyword": keyword,
                        "score": config["score"],
                    })

        if sector_matches:
            # Dedupe: keep highest score per CNAE
            best = {}
            for sm in sector_matches:
                if sm["cnae"] not in best or sm["score"] > best[sm["cnae"]]["score"]:
                    best[sm["cnae"]] = sm

            cnae_codes = sorted(best.keys())
            avg_score = round(sum(v["score"] for v in best.values()) / len(best))
            keywords_used = list(set(v["keyword"] for v in best.values()))

            await db.cnmv_entities.update_one(
                {"nif": e["nif"]},
                {"$set": {
                    "cnae_codes": cnae_codes,
                    "sector_confidence": {
                        "level": "B",
                        "score": avg_score,
                        "source_type": "internal_ai",
                        "reason": f"Clasificacion inferida por keywords: {', '.join(keywords_used)}",
                        "keywords_matched": keywords_used,
                        "per_cnae": {v["cnae"]: {"score": v["score"], "keyword": v["keyword"]} for v in best.values()},
                    },
                    "sector_mapped_at": now,
                }}
            )
            mapped += 1
        else:
            await db.cnmv_entities.update_one(
                {"nif": e["nif"]},
                {"$set": {
                    "cnae_codes": [],
                    "sector_confidence": {
                        "level": "B",
                        "score": 50,
                        "source_type": "internal_ai",
                        "reason": "Sin keywords sectoriales. Clasificado como generalista (multi-sector).",
                        "keywords_matched": [],
                    },
                    "sector_mapped_at": now,
                }}
            )

    return {
        "status": "completed",
        "total": total,
        "sector_mapped": mapped,
        "generalist": total - mapped,
        "mapping_rate_pct": round(mapped / total * 100, 1) if total > 0 else 0,
    }


def _build_data_lineage(entity: Dict) -> Dict:
    """Build data lineage for an entity — which field comes from where."""
    lineage = {
        "name": {"source": "CNMV", "level": "A", "score": 100},
        "nif": {"source": "CNMV", "level": "A", "score": 100},
        "entity_type": {"source": "CNMV", "level": "A", "score": 100},
        "entity_type_label": {"source": "CNMV", "level": "A", "score": 100},
        "status": {"source": "CNMV", "level": "A", "score": 100},
    }

    sc = entity.get("sector_confidence", {})
    if sc:
        lineage["cnae_codes"] = {
            "source": "Internal Classification Engine",
            "level": sc.get("level", "B"),
            "score": sc.get("score", 50),
        }
        lineage["sector_classification"] = {
            "source": sc.get("source_type", "internal_ai"),
            "level": sc.get("level", "B"),
            "score": sc.get("score", 50),
            "reason": sc.get("reason", ""),
        }

    if entity.get("matched_company_id"):
        lineage["company_match"] = {
            "source": "NIF matching vs companies_master",
            "level": "A",
            "score": 100,
        }

    return lineage


async def get_buyers_for_cnae(cnae_code: str) -> Dict:
    """Find financial buyers for a CNAE sector with confidence info."""
    specialists = await db.cnmv_entities.find(
        {"cnae_codes": cnae_code, "entity_type": {"$in": list(BUYER_TYPES)}},
        {"_id": 0}
    ).sort("name", 1).to_list(200)

    specialist_managers = await db.cnmv_entities.find(
        {"cnae_codes": cnae_code, "entity_type": {"$in": list(MANAGER_TYPES)}},
        {"_id": 0}
    ).sort("name", 1).to_list(200)

    generalists = await db.cnmv_entities.find(
        {"cnae_codes": [], "entity_type": {"$in": list(BUYER_TYPES)}},
        {"_id": 0}
    ).sort("name", 1).to_list(500)

    generalist_managers = await db.cnmv_entities.find(
        {"cnae_codes": [], "entity_type": {"$in": list(MANAGER_TYPES)}},
        {"_id": 0}
    ).sort("name", 1).to_list(500)

    # Enrich all
    for e in specialists + specialist_managers + generalists + generalist_managers:
        info = CNMV_ENTITY_CATALOG.get(e.get("entity_type", ""), {})
        e["mna_relevance"] = info.get("mna_relevance", 0)
        e["mna_label"] = info.get("mna_label", "")
        e["code"] = info.get("code", e.get("entity_type", ""))

        sc = e.get("sector_confidence", {})
        per_cnae = sc.get("per_cnae", {})
        if cnae_code in per_cnae:
            e["sector_score"] = per_cnae[cnae_code]["score"]
            e["sector_keyword"] = per_cnae[cnae_code]["keyword"]
        elif e.get("cnae_codes"):
            e["sector_score"] = sc.get("score", 50)
        else:
            e["sector_score"] = 50  # generalist default

    # Sort specialists by sector confidence
    specialists.sort(key=lambda x: x.get("sector_score", 0), reverse=True)
    specialist_managers.sort(key=lambda x: x.get("sector_score", 0), reverse=True)

    # Confidence metadata for the response
    confidence = {
        "specialist_classification": {
            "level": "B",
            "method": "Keyword matching on entity names",
            "source_type": "internal_ai",
            "note": "Fondos clasificados como especialistas por coincidencia de keywords en su denominacion oficial CNMV.",
        },
        "generalist_classification": {
            "level": "B",
            "method": "Default (no sector keywords found)",
            "source_type": "internal_ai",
            "score": 50,
            "note": "Fondos sin keywords sectoriales. Potencialmente invierten en cualquier sector.",
        },
        "official_data": {
            "level": "A",
            "fields": ["name", "nif", "entity_type", "registration"],
            "source": "CNMV Registros Oficiales",
            "note": "Nombre, NIF y tipo de entidad proceden directamente de los registros oficiales de la CNMV.",
        },
    }

    return {
        "cnae_code": cnae_code,
        "specialist_funds": specialists,
        "specialist_managers": specialist_managers,
        "generalist_funds": generalists,
        "generalist_managers": generalist_managers,
        "total_specialist": len(specialists) + len(specialist_managers),
        "total_generalist": len(generalists) + len(generalist_managers),
        "total_buyers": len(specialists) + len(generalists),
        "total_managers": len(specialist_managers) + len(generalist_managers),
        "confidence": confidence,
    }


async def get_buyers_summary_by_cnae() -> List[Dict]:
    """Buyer count per CNAE."""
    pipeline = [
        {"$match": {"cnae_codes": {"$ne": []}, "entity_type": {"$in": list(BUYER_TYPES)}}},
        {"$unwind": "$cnae_codes"},
        {"$group": {"_id": "$cnae_codes", "specialist_count": {"$sum": 1}}},
        {"$sort": {"specialist_count": -1}},
    ]
    specialists = await db.cnmv_entities.aggregate(pipeline).to_list(100)

    generalist_count = await db.cnmv_entities.count_documents(
        {"cnae_codes": [], "entity_type": {"$in": list(BUYER_TYPES)}}
    )

    return [{
        "cnae_code": s["_id"],
        "specialist_buyers": s["specialist_count"],
        "generalist_buyers": generalist_count,
        "total_buyers": s["specialist_count"] + generalist_count,
    } for s in specialists]


async def get_confidence_stats() -> Dict:
    """Get overall confidence stats for the CNMV module."""
    total = await db.cnmv_entities.count_documents({})

    # Level A: official CNMV data (all entities have this for name, NIF, type)
    level_a = total  # All entities have official data

    # Level B: inferred sector
    level_b_mapped = await db.cnmv_entities.count_documents(
        {"sector_confidence.level": "B", "cnae_codes": {"$ne": []}}
    )
    level_b_generalist = await db.cnmv_entities.count_documents(
        {"sector_confidence.level": "B", "cnae_codes": []}
    )

    # Level C: manually validated (future)
    level_c = await db.cnmv_entities.count_documents(
        {"sector_confidence.level": "C"}
    )

    # Average confidence
    pipeline = [
        {"$match": {"sector_confidence.score": {"$exists": True}}},
        {"$group": {"_id": None, "avg": {"$avg": "$sector_confidence.score"}}},
    ]
    avg_result = await db.cnmv_entities.aggregate(pipeline).to_list(1)
    avg_confidence = round(avg_result[0]["avg"], 1) if avg_result else 0

    return {
        "total_entities": total,
        "official_data_level_a": level_a,
        "inferred_sector_level_b": level_b_mapped,
        "generalist_level_b": level_b_generalist,
        "validated_level_c": level_c,
        "avg_confidence_score": avg_confidence,
        "sector_coverage_pct": round(level_b_mapped / total * 100, 1) if total > 0 else 0,
    }
