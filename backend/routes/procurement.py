"""Public Procurement — Routes for contract ingestion, CPV scope, and company matching."""

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from typing import Optional, Dict
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user
from services.procurement_connector import parse_and_ingest_csv, INITIAL_CPV_SCOPE
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/public-procurement", tags=["public_procurement"])


# ══════════════════════════════════════════
# CACHE + total-count sin escaneo
# ──────────────────────────────────────────
# Alerta real de Atlas ("Query Targeting", scanned/returned 7.100,7 en Arroba-pro):
# la causa era `count_documents({})` sin índice repetido cada 5-10 min en /status,
# /overview (pública) y /validation-report — cada uno un COLLSCAN completo de 659k+
# contratos. Arreglo: (1) `_total_contracts()` usa estimated_document_count() (lee
# metadatos de la colección, sin escaneo) con fallback honesto a count_documents({});
# (2) cache en memoria con TTL por ruta, invalidada al ingerir (/sync, /sync-placsp).
# Los conteos FILTRADOS internos (matched/pending/agregados) NO se tocan: siguen igual,
# solo se cachea la respuesta completa de cada endpoint.
_STATUS_CACHE: Dict = {"data": None, "ts": 0.0, "ttl": 60}
_OVERVIEW_CACHE: Dict = {"data": None, "ts": 0.0, "ttl": 600}
_VALIDATION_CACHE: Dict = {"data": None, "ts": 0.0, "ttl": 600}


async def _total_contracts() -> int:
    """Total de contratos SIN COLLSCAN: estimated_document_count() lee los metadatos
    de la colección. Fallback a count_documents({}) si el driver/servidor no lo soporta."""
    try:
        return await db.public_procurement_contracts.estimated_document_count()
    except Exception:
        return await db.public_procurement_contracts.count_documents({})


def _cache_get(cache: Dict):
    if cache["data"] is not None and (time.time() - cache["ts"]) < cache["ttl"]:
        return cache["data"]
    return None


def _cache_set(cache: Dict, data):
    cache["data"] = data
    cache["ts"] = time.time()
    return data


def _invalidate_procurement_caches():
    """Se llama tras cada ingesta para que /status, /overview y /validation-report
    reflejen los nuevos contratos en la siguiente petición (no esperan al TTL)."""
    for c in (_STATUS_CACHE, _OVERVIEW_CACHE, _VALIDATION_CACHE):
        c["data"] = None
        c["ts"] = 0.0


# ══════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════

@router.get("/status")
async def procurement_status(user=Depends(get_current_user)):
    cached = _cache_get(_STATUS_CACHE)
    if cached is not None:
        return cached
    total = await _total_contracts()
    matched = await db.public_procurement_contracts.count_documents({"matched_company_id": {"$ne": None}})
    pending = await db.public_procurement_contracts.count_documents({"review_status": "pending_review"})
    visible = await db.public_procurement_contracts.count_documents({"visible_in_valuo": True})
    cpv_active = await db.procurement_cpv_scope.count_documents({"enabled": True})

    total_amount = 0
    pipeline = [{"$match": {"amount": {"$ne": None}}}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
    agg = await db.public_procurement_contracts.aggregate(pipeline).to_list(1)
    if agg:
        total_amount = round(agg[0]["total"], 2)

    last_sync = await db.procurement_sync_logs.find_one({}, {"_id": 0, "synced_at": 1}, sort=[("synced_at", -1)])
    last_log = await db.procurement_sync_logs.find_one({}, {"_id": 0}, sort=[("synced_at", -1)])

    return _cache_set(_STATUS_CACHE, {
        "provider": "public_procurement",
        "name": "Contratacion Publica",
        "total_contracts": total,
        "matched_companies": matched,
        "pending_review": pending,
        "visible_in_valuo": visible,
        "total_amount_eur": total_amount,
        "cpv_codes_active": cpv_active,
        "last_sync_at": last_sync.get("synced_at") if last_sync else None,
        "last_sync_stats": last_log,
    })


@router.get("/overview")
async def procurement_overview():
    """Comprehensive overview for the Contratacion Publica page. Public endpoint."""
    cached = _cache_get(_OVERVIEW_CACHE)
    if cached is not None:
        return cached
    total = await _total_contracts()
    if total == 0:
        return {"total_contracts": 0}

    # KPIs
    amount_agg = await db.public_procurement_contracts.aggregate([
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$amount", 0]}},
                    "avg": {"$avg": {"$ifNull": ["$amount", 0]}},
                    "max": {"$max": "$amount"}}}
    ]).to_list(1)
    amount = amount_agg[0] if amount_agg else {}

    with_nif = await db.public_procurement_contracts.count_documents({"awardee_tax_id": {"$nin": [None, ""]}})
    unique_nifs = len(await db.public_procurement_contracts.distinct("awardee_tax_id", {"awardee_tax_id": {"$nin": [None, ""]}}))
    unique_buyers = len(await db.public_procurement_contracts.distinct("buyer_name", {"buyer_name": {"$nin": [None, ""]}}))

    # Contract type distribution
    type_agg = await db.public_procurement_contracts.aggregate([
        {"$group": {"_id": "$contract_type", "count": {"$sum": 1}, "amount": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        {"$sort": {"count": -1}},
    ]).to_list(10)

    # Top CPV
    cpv_agg = await db.public_procurement_contracts.aggregate([
        {"$match": {"cpv_code": {"$nin": [None, ""]}}},
        {"$group": {"_id": {"$substr": ["$cpv_code", 0, 2]}, "count": {"$sum": 1},
                    "amount": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        {"$sort": {"count": -1}},
        {"$limit": 12},
    ]).to_list(12)

    # NIF type breakdown (count contracts, not unique NIFs — faster and no substr issue)
    empresas_ab = await db.public_procurement_contracts.count_documents(
        {"awardee_tax_id": {"$regex": "^[AB]"}}
    )
    personas = await db.public_procurement_contracts.count_documents(
        {"awardee_tax_id": {"$regex": "^[0-9XYZ]"}}
    )

    # Field coverage
    fields = {
        "expediente": await db.public_procurement_contracts.count_documents({"expediente": {"$nin": [None, ""]}}),
        "cpv_code": await db.public_procurement_contracts.count_documents({"cpv_code": {"$nin": [None, ""]}}),
        "contract_type": await db.public_procurement_contracts.count_documents({"contract_type": {"$nin": [None, ""]}}),
        "award_date": await db.public_procurement_contracts.count_documents({"award_date": {"$nin": [None, ""]}}),
        "publication_date": await db.public_procurement_contracts.count_documents({"publication_date": {"$nin": [None, ""]}}),
        "buyer_name": await db.public_procurement_contracts.count_documents({"buyer_name": {"$nin": [None, ""]}}),
        "buyer_nif": await db.public_procurement_contracts.count_documents({"buyer_nif": {"$nin": [None, ""]}}),
        "buyer_city": await db.public_procurement_contracts.count_documents({"buyer_city": {"$nin": [None, ""]}}),
        "awardee_name": await db.public_procurement_contracts.count_documents({"awardee_name": {"$nin": [None, ""]}}),
        "awardee_tax_id": with_nif,
        "amount": await db.public_procurement_contracts.count_documents({"amount": {"$gt": 0}}),
    }

    # Economic Intelligence metrics
    econ_metrics = await db.economic_metrics.count_documents({"source": "procurement"})
    econ_signals = await db.economic_signals.count_documents({"signal_type": "public_demand"})

    # Last sync
    last_sync = await db.procurement_sync_logs.find_one({}, {"_id": 0}, sort=[("synced_at", -1)])

    return _cache_set(_OVERVIEW_CACHE, {
        "total_contracts": total,
        "total_amount_eur": round(amount.get("total", 0), 2),
        "avg_amount_eur": round(amount.get("avg", 0), 2),
        "max_amount_eur": amount.get("max", 0),
        "unique_adjudicatarios": unique_nifs,
        "unique_compradores": unique_buyers,
        "contracts_with_nif": with_nif,
        "contracts_with_nif_pct": round(with_nif / total * 100, 1) if total > 0 else 0,
        "empresas_sa_sl": empresas_ab,
        "personas_fisicas": personas,
        "contract_types": [{"type": t["_id"] or "sin_tipo", "count": t["count"],
                            "amount": round(t["amount"], 2)} for t in type_agg],
        "top_cpv": [{"cpv": c["_id"], "count": c["count"],
                     "amount": round(c["amount"], 2)} for c in cpv_agg],
        "field_coverage": {k: {"count": v, "pct": round(v / total * 100, 1)} for k, v in fields.items()},
        "economic_intelligence": {"metrics": econ_metrics, "signals": econ_signals},
        "last_sync": last_sync,
    })


# ══════════════════════════════════════════
# CONTRACTS
# ══════════════════════════════════════════

@router.get("/contracts")
async def list_contracts(
    search: Optional[str] = None,
    matched: Optional[bool] = None,
    company_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    query = {}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"awardee_name": {"$regex": search, "$options": "i"}},
            {"buyer_name": {"$regex": search, "$options": "i"}},
        ]
    if matched is True:
        query["matched_company_id"] = {"$ne": None}
    elif matched is False:
        query["matched_company_id"] = None
    if company_id:
        query["matched_company_id"] = company_id

    total = await db.public_procurement_contracts.count_documents(query)
    contracts = await db.public_procurement_contracts.find(query, {"_id": 0}).sort("award_date", -1).skip(offset).limit(limit).to_list(limit)
    return {"contracts": contracts, "total": total}


@router.get("/contracts/{contract_id}")
async def get_contract(contract_id: str, user=Depends(get_current_user)):
    c = await db.public_procurement_contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Contrato no encontrado")
    return c


@router.get("/company/{company_id}")
async def company_procurement(company_id: str, user=Depends(get_current_user)):
    """Get procurement summary for a company."""
    contracts = await db.public_procurement_contracts.find(
        {"matched_company_id": company_id}, {"_id": 0}
    ).sort("award_date", -1).to_list(100)

    total_amount = sum(c.get("amount", 0) or 0 for c in contracts)
    buyers = {}
    cpvs = {}
    for c in contracts:
        b = c.get("buyer_name", "Desconocido")
        buyers[b] = buyers.get(b, 0) + 1
        cpv = c.get("cpv_code", "?")
        cpvs[cpv] = cpvs.get(cpv, 0) + 1

    return {
        "company_id": company_id,
        "total_contracts": len(contracts),
        "total_amount_eur": round(total_amount, 2),
        "top_buyers": sorted(buyers.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_cpvs": sorted(cpvs.items(), key=lambda x: x[1], reverse=True)[:5],
        "last_award": contracts[0].get("award_date") if contracts else None,
        "contracts": contracts[:20],
    }


# ══════════════════════════════════════════
# CPV SCOPE
# ══════════════════════════════════════════

@router.get("/cpv-scope")
async def list_cpv_scope(user=Depends(get_current_user)):
    scope = await db.procurement_cpv_scope.find({}, {"_id": 0}).sort("cpv", 1).to_list(100)
    if not scope:
        await _seed_cpv_scope()
        scope = await db.procurement_cpv_scope.find({}, {"_id": 0}).sort("cpv", 1).to_list(100)
    return {"cpv_scope": scope, "total": len(scope)}


@router.post("/cpv-scope/{cpv}/enable")
async def enable_cpv(cpv: str, user=Depends(get_current_user)):
    await db.procurement_cpv_scope.update_one({"cpv": cpv}, {"$set": {"enabled": True, "updated_at": now_iso()}})
    return {"status": "enabled", "cpv": cpv}


@router.post("/cpv-scope/{cpv}/disable")
async def disable_cpv(cpv: str, user=Depends(get_current_user)):
    await db.procurement_cpv_scope.update_one({"cpv": cpv}, {"$set": {"enabled": False, "updated_at": now_iso()}})
    return {"status": "disabled", "cpv": cpv}


# ══════════════════════════════════════════
# SYNC
# ══════════════════════════════════════════

@router.post("/sync")
async def sync_procurement(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload a CSV dataset from datos.gob.es for ingestion."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "Solo se aceptan ficheros CSV")

    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            csv_text = content.decode("latin-1")
        except Exception:
            raise HTTPException(400, "No se puede leer el fichero. Encoding no soportado.")

    email = user.get("email", user.get("id"))
    source_url = f"upload:{file.filename}"

    result = await parse_and_ingest_csv(csv_text, source_url, email)
    _invalidate_procurement_caches()
    return result


@router.get("/sync-logs")
async def list_sync_logs(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    logs = await db.procurement_sync_logs.find({}, {"_id": 0}).sort("synced_at", -1).limit(limit).to_list(limit)
    return {"logs": logs}


@router.post("/sync-placsp")
async def sync_placsp_endpoint(
    years: str = Query(None, description="Comma-separated years, e.g. '2025,2026'"),
    dataset: str = Query("menores", description="menores, licitaciones, or agregadas"),
    max_files: int = Query(None, description="Limit atom files per ZIP (for testing)"),
    user=Depends(get_current_user),
):
    """Sync REAL data from PLACSP official ZIPs (Atom XML CODICE 2.07)."""
    from services.placsp_connector import sync_placsp

    year_list = None
    if years:
        year_list = [int(y.strip()) for y in years.split(",")]

    result = await sync_placsp(years=year_list, dataset=dataset, max_files=max_files)
    _invalidate_procurement_caches()
    return result


# ══════════════════════════════════════════
# VALIDATION REPORT
# ══════════════════════════════════════════

@router.get("/validation-report")
async def validation_report(user=Depends(get_current_user)):
    """Full validation report for procurement data quality."""
    cached = _cache_get(_VALIDATION_CACHE)
    if cached is not None:
        return cached
    total = await _total_contracts()
    matched = await db.public_procurement_contracts.count_documents({"matched_company_id": {"$ne": None}})
    pending = await db.public_procurement_contracts.count_documents({"review_status": "pending_review"})
    unmatched = await db.public_procurement_contracts.count_documents({"review_status": "unmatched"})
    auto_matched = await db.public_procurement_contracts.count_documents({"review_status": "auto_matched"})

    # Amount stats
    amt_pipeline = [
        {"$match": {"amount": {"$ne": None}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "avg": {"$avg": "$amount"}, "count": {"$sum": 1}}}
    ]
    amt = await db.public_procurement_contracts.aggregate(amt_pipeline).to_list(1)
    amt = amt[0] if amt else {"total": 0, "avg": 0, "count": 0}

    matched_amt_pipeline = [
        {"$match": {"amount": {"$ne": None}, "matched_company_id": {"$ne": None}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    matched_amt = await db.public_procurement_contracts.aggregate(matched_amt_pipeline).to_list(1)
    matched_amount = matched_amt[0]["total"] if matched_amt else 0

    # Top adjudicatarios
    awardee_pipeline = [
        {"$group": {"_id": "$awardee_name", "count": {"$sum": 1}, "total": {"$sum": {"$ifNull": ["$amount", 0]}}, "matched": {"$first": "$matched_company_id"}}},
        {"$sort": {"total": -1}}, {"$limit": 10}
    ]
    top_awardees = await db.public_procurement_contracts.aggregate(awardee_pipeline).to_list(10)

    # Top compradores
    buyer_pipeline = [
        {"$group": {"_id": "$buyer_name", "count": {"$sum": 1}, "total": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        {"$sort": {"total": -1}}, {"$limit": 10}
    ]
    top_buyers = await db.public_procurement_contracts.aggregate(buyer_pipeline).to_list(10)

    # Top CPVs
    cpv_pipeline = [
        {"$group": {"_id": "$cpv_code", "count": {"$sum": 1}, "total": {"$sum": {"$ifNull": ["$amount", 0]}}}},
        {"$sort": {"count": -1}}, {"$limit": 10}
    ]
    top_cpvs = await db.public_procurement_contracts.aggregate(cpv_pipeline).to_list(10)

    # Match quality
    cif_matches = await db.public_procurement_contracts.count_documents({
        "match_confidence": {"$gte": 95}, "matched_company_id": {"$ne": None}
    })
    name_matches = await db.public_procurement_contracts.count_documents({
        "match_confidence": {"$gte": 70, "$lt": 95}, "matched_company_id": {"$ne": None}
    })

    # Companies with procurement
    companies_pipeline = [
        {"$match": {"matched_company_id": {"$ne": None}}},
        {"$group": {"_id": "$matched_company_id"}},
        {"$count": "total"}
    ]
    companies_with = await db.public_procurement_contracts.aggregate(companies_pipeline).to_list(1)
    companies_count = companies_with[0]["total"] if companies_with else 0

    return _cache_set(_VALIDATION_CACHE, {
        "summary": {
            "total_contracts": total,
            "matched": matched,
            "auto_matched": auto_matched,
            "pending_review": pending,
            "unmatched": unmatched,
            "match_rate_pct": round(matched / max(total, 1) * 100, 1),
        },
        "amounts": {
            "total_eur": round(amt.get("total", 0), 2),
            "matched_eur": round(matched_amount, 2),
            "average_eur": round(amt.get("avg", 0), 2),
            "with_amount": amt.get("count", 0),
        },
        "match_quality": {
            "cif_exact_matches": cif_matches,
            "name_matches": name_matches,
            "companies_with_procurement": companies_count,
        },
        "top_awardees": [{"name": a["_id"], "contracts": a["count"], "amount": round(a["total"], 2), "matched": a.get("matched") is not None} for a in top_awardees],
        "top_buyers": [{"name": b["_id"], "contracts": b["count"], "amount": round(b["total"], 2)} for b in top_buyers],
        "top_cpvs": [{"cpv": c["_id"], "contracts": c["count"], "amount": round(c["total"], 2)} for c in top_cpvs],
    })


# ══════════════════════════════════════════
# INTERNAL
# ══════════════════════════════════════════

async def _seed_cpv_scope():
    now = now_iso()
    for cpv in INITIAL_CPV_SCOPE:
        existing = await db.procurement_cpv_scope.find_one({"cpv": cpv["cpv"]})
        if not existing:
            await db.procurement_cpv_scope.insert_one({
                **cpv, "enabled": True, "category_mapping": None,
                "created_at": now, "updated_at": now,
            })
