"""Data Providers Hub — Governance, audit, exclusions, health, and management."""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from pydantic import BaseModel
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user
from services.ine_connector import (
    get_available_operations, get_operation_tables, get_table_data,
    get_table_groups, sync_ine_table, KNOWN_OPERATIONS
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data-providers", tags=["data_providers"])

VALID_PROVIDERS = {"borme", "ine", "iberinform"}
REASON_CODES = ["wrong_company_match", "duplicate", "irrelevant", "outdated", "low_confidence", "outside_scope", "incorrect_source", "manual_quality_control", "other"]

# Provider → collection mapping for records
# NOTE (2026-07-23): "iberinform" used to point at provider_files/file_id — a leftover from
# the old single-file-upload mechanism. The real ingestion pipelines built this session
# (bootstrap-tab, upload-delivery, process-tab-directory) write companies directly into
# iberinform_companies and never touch provider_files, so this governance page always showed
# 0 registros / Inactivo regardless of how much real data had been loaded. Repointed to the
# actual company records, at the same per-record granularity BORME/INE already use, keyed by
# cif_normalized (NOT company_id — company_id is regenerated on every re-ingestion run in
# process_real_iberinform_tab_directory(), so it isn't stable across monthly deliveries;
# cif_normalized is Daniel's confirmed authoritative company identifier).
PROVIDER_COLLECTIONS = {
    "borme": "borme_events",
    "ine": "ine_observations",
    "iberinform": "iberinform_companies",
}
PROVIDER_ID_FIELDS = {
    "borme": "idempotency_key",
    "ine": "observation_id",
    "iberinform": "cif_normalized",
}


class ExcludeRequest(BaseModel):
    reason_code: str
    reason_text: Optional[str] = None
    related_company_name: Optional[str] = None

class ReassignRequest(BaseModel):
    reassign_to_company_id: str
    reassign_to_company_name: Optional[str] = None
    reason_text: Optional[str] = None


# ══════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════

@router.get("/health")
async def providers_health(user=Depends(get_current_user)):
    """Real health check for all providers."""
    providers = []

    # BORME
    borme_total = await db.borme_events.count_documents({})
    borme_excluded = await db.provider_exclusions.count_documents({"provider": "borme", "action": "exclude"})
    borme_last = await db.borme_summaries.find_one({}, {"_id": 0, "publication_date": 1}, sort=[("publication_date", -1)])
    borme_last_err = await db.borme_summaries.find_one({"status": {"$in": ["error", "failed"]}}, {"_id": 0}, sort=[("publication_date", -1)])
    providers.append({
        "provider": "borme", "name": "BORME", "status": "healthy",
        "api_reachable": True,
        "last_success_at": borme_last.get("publication_date") if borme_last else None,
        "last_error_at": None, "last_error_message": None,
        "records_total": borme_total,
        "records_visible_in_valuo": borme_total - borme_excluded,
        "records_excluded": borme_excluded,
        "pending_review": 0,
        "sync_status": "idle",
    })

    # INE
    ine_total = await db.ine_observations.count_documents({})
    ine_excluded = await db.provider_exclusions.count_documents({"provider": "ine", "action": "exclude"})
    ine_status = await db.data_provider_status.find_one({"provider": "ine"}, {"_id": 0})
    if isinstance(ine_status, str):
        ine_status = None
    ine_last_log = await db.ine_sync_logs.find_one({"status": "completed"}, {"_id": 0, "synced_at": 1}, sort=[("synced_at", -1)])
    ine_last_err = await db.ine_sync_logs.find_one({"status": "error"}, {"_id": 0, "synced_at": 1, "error": 1}, sort=[("synced_at", -1)])
    providers.append({
        "provider": "ine", "name": "INE",
        "status": ine_status.get("status", "inactive") if isinstance(ine_status, dict) else "inactive",
        "api_reachable": True,
        "last_success_at": ine_last_log.get("synced_at") if ine_last_log else None,
        "last_error_at": ine_last_err.get("synced_at") if ine_last_err else None,
        "last_error_message": ine_last_err.get("error") if ine_last_err else None,
        "records_total": ine_total,
        "records_visible_in_valuo": ine_total - ine_excluded,
        "records_excluded": ine_excluded,
        "pending_review": 0,
        "sync_status": "idle",
    })

    # Iberinform — counts real companies ingested via bootstrap-tab/upload-delivery
    # (iberinform_companies, excluding the synthetic seed), not the old provider_files
    # upload-tracking mechanism the real pipelines never write to.
    ib = await db.data_providers.find_one({"provider_id": "iberinform"}, {"_id": 0, "api_key": 0})
    ib_total = await db.iberinform_companies.count_documents({"source": {"$ne": "iberinform_synthetic"}})
    ib_excluded = await db.provider_exclusions.count_documents({"provider": "iberinform", "action": "exclude"})
    ib_last = await db.iberinform_companies.find_one(
        {"source": {"$ne": "iberinform_synthetic"}}, {"_id": 0, "imported_at": 1, "updated_at": 1},
        sort=[("updated_at", -1)])
    ib_last_sync = ((ib_last or {}).get("updated_at") or (ib_last or {}).get("imported_at")
                    or (ib.get("last_upload_at") if ib else None))
    providers.append({
        "provider": "iberinform", "name": "Iberinform",
        "status": "healthy" if ib_total > 0 else "inactive",
        "api_reachable": True,
        "last_success_at": ib_last_sync,
        "last_error_at": None, "last_error_message": None,
        "records_total": ib_total,
        "records_visible_in_valuo": ib_total - ib_excluded,
        "records_excluded": ib_excluded,
        "pending_review": 0,
        "sync_status": "idle",
    })

    return {"providers": providers}


# ══════════════════════════════════════════
# GENERIC RECORDS
# ══════════════════════════════════════════

@router.get("/{provider}/records")
async def list_provider_records(
    provider: str,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user)
):
    """List records from a provider with exclusion status."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(400, f"Invalid provider. Must be one of: {VALID_PROVIDERS}")

    coll = db[PROVIDER_COLLECTIONS[provider]]
    query = {}
    if search:
        if provider == "borme":
            query["$or"] = [{"company_name": {"$regex": search, "$options": "i"}}, {"event_text": {"$regex": search, "$options": "i"}}]
        elif provider == "ine":
            query["$or"] = [{"series_name": {"$regex": search, "$options": "i"}}, {"cnae_code": {"$regex": search, "$options": "i"}}]
        elif provider == "iberinform":
            query["$or"] = [{"legal_name": {"$regex": search, "$options": "i"}}, {"cif": {"$regex": search, "$options": "i"}}]

    total = await coll.count_documents(query)
    records = await coll.find(query, {"_id": 0}).sort([("_id", -1)]).skip(offset).limit(limit).to_list(limit)

    # Get exclusion status for these records
    id_field = PROVIDER_ID_FIELDS[provider]
    record_ids = [r.get(id_field) for r in records if r.get(id_field)]
    exclusions = {}
    if record_ids:
        excl_list = await db.provider_exclusions.find(
            {"provider": provider, "source_record_id": {"$in": record_ids}, "action": "exclude"},
            {"_id": 0}
        ).to_list(len(record_ids))
        exclusions = {e["source_record_id"]: e for e in excl_list}

    for r in records:
        rid = r.get(id_field)
        excl = exclusions.get(rid)
        r["_record_id"] = rid
        r["excluded_from_valuo"] = excl is not None
        r["exclusion_reason"] = excl.get("reason_code") if excl else None
        r["valuo_visibility_status"] = "excluded" if excl else "visible"

    return {"records": records, "total": total}


@router.get("/{provider}/records/{record_id}")
async def get_provider_record(provider: str, record_id: str, user=Depends(get_current_user)):
    """Get a single record with full detail including exclusion and matching info."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(400, "Invalid provider")

    coll = db[PROVIDER_COLLECTIONS[provider]]
    id_field = PROVIDER_ID_FIELDS[provider]
    record = await coll.find_one({id_field: record_id}, {"_id": 0})
    if not record:
        raise HTTPException(404, "Record not found")

    # Exclusion status
    excl = await db.provider_exclusions.find_one(
        {"provider": provider, "source_record_id": record_id, "action": "exclude"}, {"_id": 0}
    )
    record["_record_id"] = record_id
    record["excluded_from_valuo"] = excl is not None
    record["exclusion_info"] = excl
    record["valuo_visibility_status"] = "excluded" if excl else "visible"

    # Audit history
    audits = await db.provider_exclusions.find(
        {"provider": provider, "source_record_id": record_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    record["audit_history"] = audits

    return record


@router.post("/{provider}/records/{record_id}/exclude")
async def exclude_record(provider: str, record_id: str, req: ExcludeRequest, user=Depends(get_current_user)):
    """Exclude a record from Valuo."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(400, "Invalid provider")
    if req.reason_code not in REASON_CODES:
        raise HTTPException(400, f"Invalid reason_code. Must be one of: {REASON_CODES}")

    now = now_iso()
    email = user.get("email", user.get("id"))

    await db.provider_exclusions.insert_one({
        "exclusion_id": new_id(),
        "provider": provider,
        "source_record_id": record_id,
        "source_type": provider,
        "related_company_name": req.related_company_name,
        "action": "exclude",
        "reason_code": req.reason_code,
        "reason_text": req.reason_text,
        "excluded_from_valuo": True,
        "reassigned_to_company_id": None,
        "reassigned_to_company_name": None,
        "created_by": email,
        "created_at": now,
        "updated_at": now,
    })

    return {"status": "excluded", "record_id": record_id, "provider": provider}


@router.post("/{provider}/records/{record_id}/restore")
async def restore_record(provider: str, record_id: str, user=Depends(get_current_user)):
    """Restore an excluded record back to Valuo."""
    now = now_iso()
    email = user.get("email", user.get("id"))

    # Remove active exclusion
    result = await db.provider_exclusions.delete_many(
        {"provider": provider, "source_record_id": record_id, "action": "exclude"}
    )

    # Add restore audit entry
    await db.provider_exclusions.insert_one({
        "exclusion_id": new_id(),
        "provider": provider,
        "source_record_id": record_id,
        "action": "restore",
        "reason_code": "manual_restore",
        "reason_text": None,
        "excluded_from_valuo": False,
        "created_by": email,
        "created_at": now,
        "updated_at": now,
    })

    return {"status": "restored", "record_id": record_id, "exclusions_removed": result.deleted_count}


@router.post("/{provider}/records/{record_id}/reassign")
async def reassign_record(provider: str, record_id: str, req: ReassignRequest, user=Depends(get_current_user)):
    """Reassign a record to a different company."""
    now = now_iso()
    email = user.get("email", user.get("id"))

    await db.provider_exclusions.insert_one({
        "exclusion_id": new_id(),
        "provider": provider,
        "source_record_id": record_id,
        "action": "reassign",
        "reason_code": "wrong_company_match",
        "reason_text": f"Reassigned to {req.reassign_to_company_name or req.reassign_to_company_id}",
        "excluded_from_valuo": False,
        "reassigned_to_company_id": req.reassign_to_company_id,
        "reassigned_to_company_name": req.reassign_to_company_name,
        "created_by": email,
        "created_at": now,
        "updated_at": now,
    })

    return {"status": "reassigned", "record_id": record_id, "reassigned_to": req.reassign_to_company_id}


@router.get("/{provider}/exclusions")
async def list_exclusions(
    provider: str,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user)
):
    """List all exclusions for a provider."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(400, "Invalid provider")

    exclusions = await db.provider_exclusions.find(
        {"provider": provider}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    total = await db.provider_exclusions.count_documents({"provider": provider})

    return {"exclusions": exclusions, "total": total}


# ══════════════════════════════════════════
# OVERVIEW / STATUS
# ══════════════════════════════════════════

@router.get("/status")
async def providers_status(user=Depends(get_current_user)):
    """Unified status for all data providers."""
    providers = []

    # BORME
    borme_events = await db.borme_events.count_documents({})
    borme_last = await db.borme_summaries.find_one({}, {"_id": 0, "publication_date": 1}, sort=[("publication_date", -1)])
    providers.append({
        "provider": "borme", "name": "BORME",
        "description": "Boletin Oficial del Registro Mercantil",
        "status": "ok", "records_count": borme_events,
        "last_sync_at": borme_last.get("publication_date") if borme_last else None,
        "health": "active",
    })

    # INE
    ine_status = await db.data_provider_status.find_one({"provider": "ine"}, {"_id": 0})
    if isinstance(ine_status, str):
        ine_status = None  # Defensive: skip corrupt records
    ine_obs = await db.ine_observations.count_documents({})
    providers.append({
        "provider": "ine", "name": "INE",
        "description": "Instituto Nacional de Estadistica",
        "status": ine_status.get("status", "inactive") if isinstance(ine_status, dict) else "inactive",
        "records_count": ine_obs,
        "last_sync_at": ine_status.get("last_sync_at") if isinstance(ine_status, dict) else None,
        "last_error": ine_status.get("last_error") if isinstance(ine_status, dict) else None,
        "health": "active" if ine_obs > 0 else "pending",
    })

    # Iberinform
    ib = await db.data_providers.find_one({"provider_id": "iberinform"}, {"_id": 0, "api_key": 0})
    ib_files = await db.provider_files.count_documents({"provider_id": "iberinform"})
    providers.append({
        "provider": "iberinform", "name": "Iberinform",
        "description": "Dataset semanal de inteligencia corporativa",
        "status": "active" if ib and ib.get("active") else "inactive",
        "records_count": ib_files,
        "last_sync_at": ib.get("last_upload_at") if ib else None,
        "health": "active" if ib_files > 0 else "pending",
    })

    return {"providers": providers}


# ══════════════════════════════════════════
# BORME STATUS
# ══════════════════════════════════════════

@router.get("/borme/status")
async def borme_status(user=Depends(get_current_user)):
    events = await db.borme_events.count_documents({})
    days = await db.borme_summaries.count_documents({})
    ma = await db.borme_events.count_documents({"event_type": "ma"})
    last = await db.borme_summaries.find_one({}, {"_id": 0}, sort=[("publication_date", -1)])
    return {
        "provider": "borme", "total_events": events, "days_processed": days,
        "ma_events": ma, "last_summary": last,
    }


# ══════════════════════════════════════════
# INE
# ══════════════════════════════════════════

@router.get("/ine/status")
async def ine_status(user=Depends(get_current_user)):
    status = await db.data_provider_status.find_one({"provider": "ine"}, {"_id": 0})
    obs_count = await db.ine_observations.count_documents({})
    tables_count = await db.ine_tables.count_documents({})
    scope = await db.ine_cnae_scope.find({}, {"_id": 0}).to_list(50)
    last_logs = await db.ine_sync_logs.find({}, {"_id": 0}).sort("synced_at", -1).limit(5).to_list(5)
    return {
        "provider": "ine",
        "status": status.get("status", "inactive") if status else "inactive",
        "observations_count": obs_count,
        "tables_registered": tables_count,
        "cnae_scope": scope,
        "last_sync_logs": last_logs,
        "known_operations": KNOWN_OPERATIONS,
    }


@router.get("/ine/operations")
async def ine_operations(user=Depends(get_current_user)):
    """List available INE operations."""
    ops = await get_available_operations()
    return {"operations": [{"id": o["Id"], "code": o.get("Cod_IOE", ""), "name": o["Nombre"]} for o in ops]}


@router.get("/ine/tables")
async def ine_tables(operation_id: int = Query(...), user=Depends(get_current_user)):
    """List tables for an INE operation."""
    tables = await get_operation_tables(operation_id)
    # Also get registered tables from DB
    registered = {t["table_id"]: t for t in await db.ine_tables.find({}, {"_id": 0}).to_list(200)}
    result = []
    for t in tables:
        tid = t["Id"]
        reg = registered.get(tid)
        result.append({
            "table_id": tid, "name": t["Nombre"],
            "registered": reg is not None,
            "dataset_type": reg.get("dataset_type") if reg else None,
            "last_sync": reg.get("last_sync_at") if reg else None,
        })
    return {"tables": result, "total": len(result)}


class INETableRegister(BaseModel):
    table_id: int
    dataset_type: str  # iass, structural, prices, labor, production
    description: Optional[str] = None
    cnae_scope: Optional[str] = None


@router.post("/ine/tables/register")
async def register_ine_table(req: INETableRegister, user=Depends(get_current_user)):
    """Register an INE table for periodic sync."""
    now = now_iso()
    await db.ine_tables.update_one(
        {"table_id": req.table_id},
        {"$set": {
            "table_id": req.table_id, "dataset_type": req.dataset_type,
            "description": req.description, "cnae_scope": req.cnae_scope,
            "active": True, "registered_at": now, "updated_at": now,
            "registered_by": user.get("email", user.get("id")),
        }},
        upsert=True
    )
    return {"status": "registered", "table_id": req.table_id}


@router.post("/ine/tables/{table_id}/sync")
async def sync_table(table_id: int, nult: int = Query(5, ge=1, le=50), user=Depends(get_current_user)):
    """Sync a specific INE table."""
    # Get registered config
    reg = await db.ine_tables.find_one({"table_id": table_id}, {"_id": 0})
    dataset_type = reg.get("dataset_type", "unknown") if reg else "unknown"
    cnae_scope = reg.get("cnae_scope") if reg else None

    result = await sync_ine_table(table_id, dataset_type, cnae_scope, nult=nult)

    if reg:
        await db.ine_tables.update_one(
            {"table_id": table_id},
            {"$set": {"last_sync_at": now_iso()}}
        )

    return result


@router.get("/ine/observations")
async def get_observations(
    cnae_code: Optional[str] = None,
    dataset_type: Optional[str] = None,
    table_id: Optional[int] = None,
    year: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000),
    user=Depends(get_current_user)
):
    """Query INE observations."""
    query = {}
    if cnae_code:
        query["cnae_code"] = {"$regex": f"^{cnae_code}"}
    if dataset_type:
        query["dataset_type"] = dataset_type
    if table_id:
        query["table_id"] = table_id
    if year:
        query["year"] = year

    total = await db.ine_observations.count_documents(query)
    obs = await db.ine_observations.find(query, {"_id": 0}).sort([("year", -1), ("period", -1)]).limit(limit).to_list(limit)
    return {"observations": obs, "total": total}


@router.get("/ine/cnae-scope")
async def get_cnae_scope(user=Depends(get_current_user)):
    """Get configured CNAE scope for INE tracking."""
    scope = await db.ine_cnae_scope.find({}, {"_id": 0}).to_list(50)
    return {"scope": scope}


class CNAEScopeEntry(BaseModel):
    cnae_code: str
    cnae_name: str
    priority: str = "high"  # high, medium, low
    notes: Optional[str] = None


@router.post("/ine/cnae-scope")
async def add_cnae_scope(req: CNAEScopeEntry, user=Depends(get_current_user)):
    """Add a CNAE code to tracking scope."""
    await db.ine_cnae_scope.update_one(
        {"cnae_code": req.cnae_code},
        {"$set": {
            "cnae_code": req.cnae_code, "cnae_name": req.cnae_name,
            "priority": req.priority, "notes": req.notes,
            "active": True, "updated_at": now_iso(),
        }},
        upsert=True
    )
    return {"status": "added", "cnae_code": req.cnae_code}


@router.get("/ine/sync-logs")
async def get_sync_logs(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    logs = await db.ine_sync_logs.find({}, {"_id": 0}).sort("synced_at", -1).limit(limit).to_list(limit)
    return {"logs": logs}


@router.get("/ine/datasets")
async def ine_datasets(user=Depends(get_current_user)):
    """Known INE datasets with status and coverage info."""
    datasets = [
        {"key": "iass", "name": "IASS — Indicadores de Actividad del Sector Servicios", "operation_id": 31,
         "description": "Evolucion de cifra de negocios, empleo y variaciones sectoriales.",
         "valuo_use": "Contexto sectorial: indice actividad, variacion anual/mensual/acumulada.",
         "metrics": ["index", "yoy_change", "mom_change", "ytd_change"]},
        {"key": "structural", "name": "Estadistica Estructural de Empresas: Servicios", "operation_id": 130,
         "description": "Ingresos agregados, personal ocupado, productividad sectorial por CNAE.",
         "valuo_use": "Tamano de mercado, productividad, benchmarks sectoriales.",
         "metrics": ["revenue", "employees", "productivity"]},
        {"key": "dirce", "name": "DIRCE — Empresas activas por CNAE y territorio", "operation_id": None,
         "description": "Numero de empresas activas por CNAE, territorio y tramo de empleados.",
         "valuo_use": "Tamano de mercado, densidad empresarial, concentracion.",
         "metrics": ["company_count", "by_size", "by_territory"]},
        {"key": "ipc", "name": "IPC — Indice de Precios al Consumo", "operation_id": None,
         "description": "Indice general y variaciones para deflactar crecimiento nominal.",
         "valuo_use": "Deflactor para calcular crecimiento real vs nominal.",
         "metrics": ["price_index", "yoy_change"]},
    ]

    for ds in datasets:
        # Check if any tables registered for this dataset
        tables = await db.ine_tables.count_documents({"dataset_type": ds["key"]})
        obs = await db.ine_observations.count_documents({"dataset_type": ds["key"]})
        last_sync = await db.ine_sync_logs.find_one(
            {"dataset_type": ds["key"], "status": "completed"}, {"_id": 0, "synced_at": 1},
            sort=[("synced_at", -1)]
        )
        ds["tables_registered"] = tables
        ds["observations"] = obs
        ds["last_sync"] = last_sync.get("synced_at") if last_sync else None
        ds["status"] = "active" if obs > 0 else "registered" if tables > 0 else "pending"

    return {"datasets": datasets}


@router.get("/ine/coverage")
async def ine_coverage(user=Depends(get_current_user)):
    """Data coverage matrix: what INE data do we have right now?"""
    pipeline = [
        {"$match": {"cnae_code": {"$ne": None}}},
        {"$group": {
            "_id": {"dataset": "$dataset_type", "metric": "$metric", "cnae": "$cnae_code", "cnae_label": "$cnae_label"},
            "count": {"$sum": 1},
            "min_year": {"$min": "$year"},
            "max_year": {"$max": "$year"},
            "last_value": {"$last": "$value"},
            "table_id": {"$first": "$table_id"},
        }},
        {"$sort": {"_id.cnae": 1, "_id.dataset": 1, "_id.metric": 1}},
    ]
    rows = await db.ine_observations.aggregate(pipeline).to_list(500)

    coverage = []
    for r in rows:
        coverage.append({
            "dataset": r["_id"]["dataset"],
            "metric": r["_id"]["metric"],
            "cnae_code": r["_id"]["cnae"],
            "cnae_label": r["_id"]["cnae_label"],
            "periods": r["count"],
            "year_range": f"{r['min_year']}-{r['max_year']}" if r["min_year"] != r["max_year"] else str(r["min_year"]),
            "last_value": r["last_value"],
            "table_id": r["table_id"],
            "status": "active",
        })

    return {"coverage": coverage, "total": len(coverage)}


@router.get("/ine/cnae-search")
async def cnae_search(q: str = Query("", min_length=0), user=Depends(get_current_user)):
    """Search available CNAEs from current observations."""
    pipeline = [
        {"$match": {"cnae_code": {"$ne": None}}},
        {"$group": {
            "_id": {"code": "$cnae_code", "label": "$cnae_label"},
            "observations": {"$sum": 1},
            "datasets": {"$addToSet": "$dataset_type"},
            "last_sync": {"$max": "$fetched_at"},
        }},
        {"$sort": {"_id.code": 1}},
    ]
    all_cnaes = await db.ine_observations.aggregate(pipeline).to_list(200)

    # Get active scope
    scope = {s["cnae_code"] for s in await db.ine_cnae_scope.find({"active": True}, {"_id": 0, "cnae_code": 1}).to_list(100)}

    results = []
    for c in all_cnaes:
        code = c["_id"]["code"]
        label = c["_id"]["label"] or ""
        if q and q.lower() not in code.lower() and q.lower() not in label.lower():
            continue
        results.append({
            "cnae_code": code,
            "cnae_label": label,
            "observations": c["observations"],
            "datasets": c["datasets"],
            "last_sync": c["last_sync"],
            "active": code in scope,
        })

    return {"cnaes": results, "total": len(results)}



# ══════════════════════════════════════════
# MARKET CONTEXT (Valuo consumption)
# ══════════════════════════════════════════

@router.get("/ine/market-context")
async def ine_market_context(cnae_code: str = Query("73"), user=Depends(get_current_user)):
    """Aggregated market context for a CNAE code, consumable by Valuo."""
    obs = await db.ine_observations.find(
        {"cnae_code": {"$regex": f"^{cnae_code}"}},
        {"_id": 0}
    ).sort([("year", -1), ("period", -1)]).to_list(500)

    if not obs:
        return {"cnae_code": cnae_code, "status": "no_data", "context": None,
                "message": "No observations found. Sync INE tables first."}

    # Group by metric
    by_metric = {}
    for o in obs:
        m = o.get("metric") or "other"
        by_metric.setdefault(m, []).append(o)

    # Build context
    context = {"cnae_code": cnae_code, "cnae_label": obs[0].get("cnae_label", "")}

    # Latest index value
    idx_obs = sorted(by_metric.get("index", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if idx_obs:
        latest = idx_obs[0]
        context["index"] = {
            "value": latest["value"], "year": latest["year"], "period": latest.get("period"),
            "series": latest["series_name"], "source_url": latest.get("source_url"),
        }
        # Historical index
        context["index_history"] = [
            {"value": o["value"], "year": o["year"], "period": o.get("period")}
            for o in idx_obs[:12]
        ]

    # YoY change
    yoy_obs = sorted(by_metric.get("yoy_change", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if yoy_obs:
        latest = yoy_obs[0]
        context["yoy_change"] = {
            "value_pct": latest["value"], "year": latest["year"], "period": latest.get("period"),
            "series": latest["series_name"],
        }
        context["yoy_history"] = [
            {"value_pct": o["value"], "year": o["year"], "period": o.get("period")}
            for o in yoy_obs[:12]
        ]

    # MoM change
    mom_obs = sorted(by_metric.get("mom_change", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if mom_obs:
        latest = mom_obs[0]
        context["mom_change"] = {
            "value_pct": latest["value"], "year": latest["year"], "period": latest.get("period"),
        }

    # YTD change
    ytd_obs = sorted(by_metric.get("ytd_change", []), key=lambda x: (x.get("year", 0), x.get("period") or 0), reverse=True)
    if ytd_obs:
        latest = ytd_obs[0]
        context["ytd_change"] = {
            "value_pct": latest["value"], "year": latest["year"], "period": latest.get("period"),
        }

    # Compute interannual from index history if available
    if len(idx_obs) >= 2:
        periods_by_year = {}
        for o in idx_obs:
            key = (o.get("year"), o.get("period"))
            periods_by_year[key] = o["value"]

        computed_yoy = []
        for o in idx_obs:
            prev_key = (o["year"] - 1, o.get("period"))
            if prev_key in periods_by_year and periods_by_year[prev_key]:
                yoy_pct = round((o["value"] - periods_by_year[prev_key]) / periods_by_year[prev_key] * 100, 2)
                computed_yoy.append({
                    "year": o["year"], "period": o.get("period"),
                    "value_current": o["value"],
                    "value_previous_year": periods_by_year[prev_key],
                    "yoy_change_pct": yoy_pct,
                })
        if computed_yoy:
            context["computed_yoy"] = computed_yoy[:12]

    # Summary
    context["data_points"] = len(obs)
    context["metrics_available"] = list(by_metric.keys())
    context["last_updated"] = obs[0].get("fetched_at")

    return {
        "cnae_code": cnae_code,
        "status": "ok",
        "context": context,
        "source": "INE - Instituto Nacional de Estadistica",
        "tables_used": list(set(o.get("table_id") for o in obs)),
    }


# ══════════════════════════════════════════
# DEBUG / AUDIT
# ══════════════════════════════════════════

@router.get("/ine/debug/observations")
async def debug_observations(cnae_code: Optional[str] = None, user=Depends(get_current_user)):
    """Debug view: observation counts by table, metric, series."""
    match = {}
    if cnae_code:
        match["cnae_code"] = {"$regex": f"^{cnae_code}"}

    # By table
    table_pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": "$table_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_table = await db.ine_observations.aggregate(table_pipeline).to_list(50)

    # By metric
    metric_pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": "$metric", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_metric = await db.ine_observations.aggregate(metric_pipeline).to_list(20)

    # By CNAE
    cnae_pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": {"cnae": "$cnae_code", "label": "$cnae_label"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_cnae = await db.ine_observations.aggregate(cnae_pipeline).to_list(50)

    # Latest periods
    period_pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": {"year": "$year", "period": "$period"}, "count": {"$sum": 1}}},
        {"$sort": {"_id.year": -1, "_id.period": -1}},
        {"$limit": 10},
    ]
    latest_periods = await db.ine_observations.aggregate(period_pipeline).to_list(10)

    # Sample series names
    sample_pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": "$series_name", "code": {"$first": "$series_code"}, "cnae": {"$first": "$cnae_code"}}},
        {"$limit": 20},
    ]
    sample_series = await db.ine_observations.aggregate(sample_pipeline).to_list(20)

    total = await db.ine_observations.count_documents(match or {})

    return {
        "total_observations": total,
        "filter": {"cnae_code": cnae_code} if cnae_code else "all",
        "by_table": [{"table_id": r["_id"], "count": r["count"]} for r in by_table],
        "by_metric": [{"metric": r["_id"], "count": r["count"]} for r in by_metric],
        "by_cnae": [{"cnae_code": r["_id"]["cnae"], "cnae_label": r["_id"]["label"], "count": r["count"]} for r in by_cnae],
        "latest_periods": [{"year": r["_id"]["year"], "period": r["_id"]["period"], "count": r["count"]} for r in latest_periods],
        "sample_series": [{"series_name": r["_id"][:80], "code": r["code"], "cnae": r["cnae"]} for r in sample_series],
    }
