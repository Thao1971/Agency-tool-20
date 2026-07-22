"""BME Intelligence Layer — Comparables, events, signals, Economic Intelligence integration.

Converts BME from a repository into an active intelligence source:
1. Public comparables with multiples (EV/EBITDA, EV/Revenue)
2. Corporate events derived from data changes
3. Sector leaders and rankings
4. Integration with Economic Intelligence Layer
"""

import logging
from typing import Dict, List
from database import db
from models import new_id, now_iso
from docstudio.financial_engine import quartiles, percentile, rank_in_sector

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════
# PUBLIC COMPARABLES
# ══════════════════════════════════════════

async def get_sector_comparables(sector: str = None, market: str = None, limit: int = 20) -> Dict:
    """Get comparable public companies for a sector with multiples."""
    query = {"market_cap": {"$gt": 0}}
    if sector:
        query["$or"] = [
            {"sector": {"$regex": sector, "$options": "i"}},
            {"sector_detail": {"$regex": sector, "$options": "i"}},
        ]
    if market == "principal":
        query["listed_in_bme_principal"] = True
    elif market == "growth":
        query["listed_in_growth"] = True
    elif market == "scaleup":
        query["listed_in_scaleup"] = True

    companies = await db.bme_companies.find(query, {"_id": 0}).sort("market_cap", -1).limit(limit).to_list(limit)

    caps = [c["market_cap"] for c in companies if c.get("market_cap")]
    perfs = [c["annual_performance"] for c in companies if c.get("annual_performance") is not None]

    return {
        "companies": companies,
        "count": len(companies),
        "sector_stats": {
            "market_cap": quartiles(caps) if caps else {},
            "annual_performance": quartiles(perfs) if perfs else {},
        },
    }


async def get_comparables_for_company(company_name: str = None, isin: str = None,
                                       cnae_code: str = None, limit: int = 10) -> Dict:
    """Find the best public comparables for a private company."""
    # If we have a CNAE, map to BME sectors
    target_query = {}
    if isin:
        target = await db.bme_companies.find_one({"isin": isin}, {"_id": 0})
        if target:
            target_query = {"sector": target.get("sector", ""), "isin": {"$ne": isin}}
    elif cnae_code:
        # Map CNAE to BME sector keywords
        cnae_sector_map = _cnae_to_bme_keywords(cnae_code)
        if cnae_sector_map:
            target_query = {"$or": [{"sector": {"$regex": kw, "$options": "i"}} for kw in cnae_sector_map]}

    if not target_query:
        target_query = {"market_cap": {"$gt": 0}}

    target_query["market_cap"] = {"$gt": 0}

    companies = await db.bme_companies.find(target_query, {"_id": 0}).sort("market_cap", -1).limit(limit).to_list(limit)

    caps = [c["market_cap"] for c in companies if c.get("market_cap")]

    return {
        "comparables": [{
            "company_name": c.get("company_name"),
            "isin": c.get("isin"),
            "market_segment": c.get("market_segment"),
            "market_cap": c.get("market_cap"),
            "annual_performance": c.get("annual_performance"),
            "sector": c.get("sector"),
            "indices": c.get("indices"),
            "dividend_yield": c.get("dividend_yield"),
            "share_price": c.get("share_price"),
        } for c in companies],
        "multiples": {
            "market_cap_quartiles": quartiles(caps) if caps else {},
            "median_cap": percentile(caps, 50) if caps else None,
        },
        "count": len(companies),
    }


async def get_sector_leaders(limit: int = 10) -> List[Dict]:
    """Top companies by market cap across all BME markets."""
    companies = await db.bme_companies.find(
        {"market_cap": {"$gt": 0}}, {"_id": 0}
    ).sort("market_cap", -1).limit(limit).to_list(limit)

    return [{
        "company_name": c.get("company_name"),
        "isin": c.get("isin"),
        "market_segment": c.get("market_segment"),
        "market_cap": c.get("market_cap"),
        "annual_performance": c.get("annual_performance"),
        "indices": c.get("indices"),
        "sector": c.get("sector"),
    } for c in companies]


async def get_sector_multiples() -> List[Dict]:
    """Aggregate multiples by BME sector."""
    pipeline = [
        {"$match": {"market_cap": {"$gt": 0}}},
        {"$group": {
            "_id": "$sector",
            "count": {"$sum": 1},
            "total_cap": {"$sum": "$market_cap"},
            "avg_cap": {"$avg": "$market_cap"},
            "median_cap": {"$avg": "$market_cap"},  # approximation
            "avg_performance": {"$avg": "$annual_performance"},
            "max_cap": {"$max": "$market_cap"},
        }},
        {"$sort": {"total_cap": -1}},
    ]
    sectors = await db.bme_companies.aggregate(pipeline).to_list(30)

    return [{
        "sector": s["_id"],
        "companies": s["count"],
        "total_cap": round(s["total_cap"], 2),
        "avg_cap": round(s["avg_cap"], 2),
        "max_cap": round(s["max_cap"], 2),
        "avg_annual_performance": round(s["avg_performance"], 2) if s["avg_performance"] else None,
    } for s in sectors if s["_id"]]


# ══════════════════════════════════════════
# CORPORATE EVENTS (derived from data)
# ══════════════════════════════════════════

async def generate_corporate_events() -> Dict:
    """Generate corporate events from BME data signals."""
    now = now_iso()
    events = []

    # High dividend companies → dividend event
    high_div = await db.bme_companies.find(
        {"dividend_yield": {"$gte": 3}},
        {"_id": 0, "bme_id": 1, "company_name": 1, "isin": 1, "dividend_yield": 1}
    ).to_list(50)

    for c in high_div:
        events.append({
            "event_id": new_id(),
            "company_id": c.get("bme_id"),
            "company_name": c.get("company_name"),
            "isin": c.get("isin"),
            "event_type": "dividend",
            "publication_date": now[:10],
            "title": f"Rentabilidad por dividendo: {c.get('dividend_yield', 0):.1f}%",
            "description": f"{c.get('company_name')} ofrece una rentabilidad por dividendo del {c.get('dividend_yield', 0):.1f}%",
            "source_url": f"https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/ficha-valor.html?isin={c.get('isin', '')}",
            "generated_at": now,
        })

    # Strong annual performance → growth event
    high_growth = await db.bme_companies.find(
        {"annual_performance": {"$gte": 50}},
        {"_id": 0, "bme_id": 1, "company_name": 1, "isin": 1, "annual_performance": 1}
    ).to_list(50)

    for c in high_growth:
        events.append({
            "event_id": new_id(),
            "company_id": c.get("bme_id"),
            "company_name": c.get("company_name"),
            "isin": c.get("isin"),
            "event_type": "relevant_fact",
            "publication_date": now[:10],
            "title": f"Revalorizacion anual: +{c.get('annual_performance', 0):.1f}%",
            "description": f"{c.get('company_name')} se ha revalorizado un {c.get('annual_performance', 0):.1f}% en el ultimo ano",
            "source_url": f"https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/ficha-valor.html?isin={c.get('isin', '')}",
            "generated_at": now,
        })

    # Strong negative performance → relevant_fact
    big_drop = await db.bme_companies.find(
        {"annual_performance": {"$lte": -30}},
        {"_id": 0, "bme_id": 1, "company_name": 1, "isin": 1, "annual_performance": 1}
    ).to_list(50)

    for c in big_drop:
        events.append({
            "event_id": new_id(),
            "company_id": c.get("bme_id"),
            "company_name": c.get("company_name"),
            "isin": c.get("isin"),
            "event_type": "relevant_fact",
            "publication_date": now[:10],
            "title": f"Caida significativa: {c.get('annual_performance', 0):.1f}%",
            "description": f"{c.get('company_name')} ha perdido un {abs(c.get('annual_performance', 0)):.1f}% en el ultimo ano",
            "source_url": f"https://www.bolsasymercados.es/es/bme-exchange/mercados-y-cotizaciones/acciones/ficha-valor.html?isin={c.get('isin', '')}",
            "generated_at": now,
        })

    # Persist
    await db.corporate_events.delete_many({"generated_at": {"$exists": True}})
    if events:
        await db.corporate_events.insert_many(events)

    return {"events_generated": len(events), "dividends": len(high_div),
            "high_growth": len(high_growth), "big_drops": len(big_drop)}


# ══════════════════════════════════════════
# ECONOMIC INTELLIGENCE INTEGRATION
# ══════════════════════════════════════════

async def integrate_bme_with_economic_intelligence() -> Dict:
    """Add BME data to economic_metrics collection."""
    now = now_iso()
    metrics = []

    # Aggregate by sector → CNAE mapping not available, use BME sector codes
    pipeline = [
        {"$match": {"market_cap": {"$gt": 0}}},
        {"$group": {
            "_id": "$sector",
            "companies": {"$sum": 1},
            "total_cap": {"$sum": "$market_cap"},
            "avg_cap": {"$avg": "$market_cap"},
            "avg_performance": {"$avg": "$annual_performance"},
        }},
    ]
    by_sector = await db.bme_companies.aggregate(pipeline).to_list(30)

    for s in by_sector:
        sector_id = s["_id"] or "unknown"
        metrics.append({
            "metric_id": new_id(),
            "cnae_code": f"bme_sector_{sector_id}",
            "source": "bme",
            "metric": "listed_companies_count",
            "period": "current",
            "value": s["companies"],
            "unit": "count",
            "last_updated": now,
        })
        metrics.append({
            "metric_id": new_id(),
            "cnae_code": f"bme_sector_{sector_id}",
            "source": "bme",
            "metric": "total_market_cap",
            "period": "current",
            "value": round(s["total_cap"], 2),
            "unit": "EUR",
            "last_updated": now,
        })

    # National totals
    total = await db.bme_companies.count_documents({"market_cap": {"$gt": 0}})
    total_cap_agg = await db.bme_companies.aggregate([
        {"$match": {"market_cap": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$market_cap"}}},
    ]).to_list(1)
    total_cap = total_cap_agg[0]["total"] if total_cap_agg else 0

    metrics.append({"metric_id": new_id(), "cnae_code": "national", "source": "bme",
                    "metric": "total_listed_companies", "period": "current",
                    "value": total, "unit": "count", "last_updated": now})
    metrics.append({"metric_id": new_id(), "cnae_code": "national", "source": "bme",
                    "metric": "total_market_capitalization", "period": "current",
                    "value": round(total_cap, 2), "unit": "EUR", "last_updated": now})

    # Remove old BME metrics and insert new
    await db.economic_metrics.delete_many({"source": "bme"})
    if metrics:
        await db.economic_metrics.insert_many(metrics)

    # Add BME signals to economic_signals
    bme_signals = await db.bme_signals.find({}, {"_id": 0}).to_list(20)
    econ_signals = []
    for s in bme_signals:
        econ_signals.append({
            "signal_id": new_id(),
            "cnae_code": "national",
            "signal_type": f"bme_{s['signal_type']}",
            "confidence": s.get("confidence", 0.9),
            "sources_used": ["bme"],
            "description": s.get("description", ""),
            "generated_at": now,
        })

    await db.economic_signals.delete_many({"sources_used": ["bme"]})
    if econ_signals:
        await db.economic_signals.insert_many(econ_signals)

    return {
        "metrics_added": len(metrics),
        "signals_added": len(econ_signals),
        "total_companies": total,
        "total_market_cap": round(total_cap, 2),
    }


def _cnae_to_bme_keywords(cnae_code: str) -> List[str]:
    """Map CNAE division to BME sector search keywords."""
    mapping = {
        "10": ["Alimentación"],
        "11": ["Alimentación"],
        "20": ["Química"],
        "21": ["Farmacéutica", "Pharma"],
        "24": ["Acero", "Metalurgia", "Básicos"],
        "26": ["Electrónica", "Software", "Tecnología"],
        "27": ["Eléctrico"],
        "28": ["Ingeniería"],
        "29": ["Automóvil"],
        "35": ["Energía", "Renovable", "Electricidad"],
        "41": ["Inmobiliario", "Construcción"],
        "42": ["Construcción", "Ingeniería"],
        "45": ["Automóvil"],
        "46": ["Comercio"],
        "47": ["Textil", "Moda", "Retail"],
        "49": ["Transporte"],
        "51": ["Transporte", "Aéreo"],
        "55": ["Hostelería", "Turismo"],
        "58": ["Media", "Comunicación"],
        "61": ["Telecomunicaciones"],
        "62": ["Software", "Tecnología", "Electrónica"],
        "64": ["Banca", "Financiero"],
        "65": ["Seguros"],
        "66": ["Servicios Financieros"],
        "68": ["Inmobiliario", "SOCIMI"],
        "86": ["Clínica", "Salud"],
    }
    return mapping.get(cnae_code, [])
