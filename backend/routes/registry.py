"""Dataset & CNAE Registry — Governed source of truth for all data providers.

NO hardcoded datasets. Everything from DB.
NO physical deletes. Always enabled=false / status=excluded.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from pydantic import BaseModel
from database import db
from models import new_id, now_iso
from auth_utils import get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/registry", tags=["registry"])


# ── Dependencies map: dataset → what breaks if disabled ──
DEPENDENCY_MAP = {
    "ine_iass": ["market_context_api", "market_snapshots", "growth_metrics", "activity_index"],
    "ine_structural": ["sector_benchmarks", "revenue_aggregates", "employee_benchmarks"],
    "ine_ipc": ["deflator", "real_growth_calculations"],
    "ine_dirce": ["market_size", "company_density", "territory_analysis"],
    "borme_events": ["ma_signals", "corporate_events", "borme_monitor"],
    "iberinform_companies": ["financial_data", "company_profiles", "scoring"],
}


# ══════════════════════════════════════════
# DATASET REGISTRY
# ══════════════════════════════════════════

@router.get("/datasets")
async def list_datasets(include_disabled: bool = False, user=Depends(get_current_user)):
    query = {} if include_disabled else {"enabled": True}
    datasets = await db.provider_datasets.find(query, {"_id": 0}).sort("provider", 1).to_list(50)

    # If empty, seed defaults
    if not datasets:
        await _seed_datasets()
        datasets = await db.provider_datasets.find(query, {"_id": 0}).sort("provider", 1).to_list(50)

    return {"datasets": datasets, "total": len(datasets)}


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, user=Depends(get_current_user)):
    ds = await db.provider_datasets.find_one({"dataset_id": dataset_id}, {"_id": 0})
    if not ds:
        raise HTTPException(404, "Dataset not found")

    # Enrich with live stats
    if ds["provider"] == "INE":
        ds["live_observations"] = await db.ine_observations.count_documents({"dataset_type": ds.get("dataset_type")})
    elif ds["provider"] == "BORME":
        ds["live_observations"] = await db.borme_events.count_documents({})
    elif ds["provider"] == "Iberinform":
        ds["live_observations"] = await db.provider_files.count_documents({"provider_id": "iberinform"})

    ds["dependencies"] = DEPENDENCY_MAP.get(dataset_id, [])
    return ds


class DatasetAction(BaseModel):
    reason: Optional[str] = None


@router.post("/datasets/{dataset_id}/activate")
async def activate_dataset(dataset_id: str, user=Depends(get_current_user)):
    now = now_iso()
    r = await db.provider_datasets.update_one(
        {"dataset_id": dataset_id},
        {"$set": {"enabled": True, "status": "active", "updated_at": now}}
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Dataset not found")
    await _audit("dataset_activated", dataset_id, user)
    return {"status": "active", "dataset_id": dataset_id}


@router.post("/datasets/{dataset_id}/disable")
async def disable_dataset(dataset_id: str, req: DatasetAction = DatasetAction(), user=Depends(get_current_user)):
    deps = DEPENDENCY_MAP.get(dataset_id, [])
    now = now_iso()
    await db.provider_datasets.update_one(
        {"dataset_id": dataset_id},
        {"$set": {"enabled": False, "status": "disabled", "updated_at": now}}
    )
    await _audit("dataset_disabled", dataset_id, user, {"reason": req.reason, "affected": deps})
    return {"status": "disabled", "dataset_id": dataset_id, "affected_dependencies": deps}


@router.post("/datasets/{dataset_id}/exclude")
async def exclude_dataset(dataset_id: str, req: DatasetAction = DatasetAction(), user=Depends(get_current_user)):
    deps = DEPENDENCY_MAP.get(dataset_id, [])
    now = now_iso()
    await db.provider_datasets.update_one(
        {"dataset_id": dataset_id},
        {"$set": {"enabled": False, "status": "excluded", "visible_in_valuo": False, "updated_at": now}}
    )
    await _audit("dataset_excluded", dataset_id, user, {"reason": req.reason})
    return {"status": "excluded", "dataset_id": dataset_id, "affected_dependencies": deps}


@router.post("/datasets/{dataset_id}/restore")
async def restore_dataset(dataset_id: str, user=Depends(get_current_user)):
    now = now_iso()
    await db.provider_datasets.update_one(
        {"dataset_id": dataset_id},
        {"$set": {"enabled": True, "status": "active", "visible_in_valuo": True, "updated_at": now}}
    )
    await _audit("dataset_restored", dataset_id, user)
    return {"status": "active", "dataset_id": dataset_id}


# ══════════════════════════════════════════
# CNAE REGISTRY
# ══════════════════════════════════════════

@router.get("/cnaes")
async def list_cnaes(include_disabled: bool = False, user=Depends(get_current_user)):
    query = {} if include_disabled else {"enabled": True}
    cnaes = await db.provider_cnaes.find(query, {"_id": 0}).sort("cnae", 1).to_list(200)
    return {"cnaes": cnaes, "total": len(cnaes)}


@router.get("/cnaes/{cnae}")
async def get_cnae(cnae: str, user=Depends(get_current_user)):
    c = await db.provider_cnaes.find_one({"cnae": cnae}, {"_id": 0})
    if not c:
        raise HTTPException(404, "CNAE not found")
    c["observations"] = await db.ine_observations.count_documents({"cnae_code": {"$regex": f"^{cnae}"}})
    return c


class CNAERemapRequest(BaseModel):
    mapped_category_name: str
    mapped_category_id: Optional[str] = None


@router.post("/cnaes/{cnae}/enable")
async def enable_cnae(cnae: str, user=Depends(get_current_user)):
    now = now_iso()
    r = await db.provider_cnaes.update_one(
        {"cnae": cnae}, {"$set": {"enabled": True, "updated_at": now}}, upsert=False
    )
    if r.matched_count == 0:
        # Auto-create if not exists
        await db.provider_cnaes.insert_one({
            "cnae": cnae, "label": "", "provider": "INE", "enabled": True,
            "visible_in_valuo": True, "market_context_enabled": True,
            "snapshot_enabled": True, "publication_enabled": True,
            "created_at": now, "updated_at": now,
        })
    await _audit("cnae_enabled", cnae, user)
    return {"status": "enabled", "cnae": cnae}


@router.post("/cnaes/{cnae}/disable")
async def disable_cnae(cnae: str, user=Depends(get_current_user)):
    now = now_iso()
    await db.provider_cnaes.update_one({"cnae": cnae}, {"$set": {"enabled": False, "updated_at": now}})
    await _audit("cnae_disabled", cnae, user)
    return {"status": "disabled", "cnae": cnae}


@router.post("/cnaes/{cnae}/exclude")
async def exclude_cnae(cnae: str, user=Depends(get_current_user)):
    now = now_iso()
    await db.provider_cnaes.update_one(
        {"cnae": cnae}, {"$set": {"enabled": False, "visible_in_valuo": False, "updated_at": now}}
    )
    await _audit("cnae_excluded", cnae, user)
    return {"status": "excluded", "cnae": cnae}


@router.post("/cnaes/{cnae}/remap")
async def remap_cnae(cnae: str, req: CNAERemapRequest, user=Depends(get_current_user)):
    now = now_iso()
    await db.provider_cnaes.update_one(
        {"cnae": cnae},
        {"$set": {
            "mapped_category_name": req.mapped_category_name,
            "mapped_category_id": req.mapped_category_id,
            "updated_at": now,
        }}
    )
    await _audit("cnae_remapped", cnae, user, {"category": req.mapped_category_name})
    return {"status": "remapped", "cnae": cnae, "category": req.mapped_category_name}


# ══════════════════════════════════════════
# DEPENDENCIES
# ══════════════════════════════════════════

@router.get("/dependencies")
async def list_dependencies(user=Depends(get_current_user)):
    """Show all dataset dependencies."""
    return {"dependencies": DEPENDENCY_MAP}


@router.get("/dependencies/{dataset_id}")
async def get_dependencies(dataset_id: str, user=Depends(get_current_user)):
    deps = DEPENDENCY_MAP.get(dataset_id, [])
    return {"dataset_id": dataset_id, "dependencies": deps, "count": len(deps)}


# ══════════════════════════════════════════
# OBSERVABILITY
# ══════════════════════════════════════════

@router.get("/health")
async def registry_health(user=Depends(get_current_user)):
    ds_total = await db.provider_datasets.count_documents({})
    ds_active = await db.provider_datasets.count_documents({"enabled": True})
    cnae_total = await db.provider_cnaes.count_documents({})
    cnae_active = await db.provider_cnaes.count_documents({"enabled": True})
    return {
        "status": "ok",
        "datasets_total": ds_total, "datasets_active": ds_active,
        "cnaes_total": cnae_total, "cnaes_active": cnae_active,
    }


@router.get("/stats")
async def registry_stats(user=Depends(get_current_user)):
    ds = await db.provider_datasets.find({}, {"_id": 0, "dataset_id": 1, "status": 1, "enabled": 1}).to_list(50)
    cnaes = await db.provider_cnaes.find({}, {"_id": 0, "cnae": 1, "enabled": 1}).to_list(200)
    audits = await db.registry_audit_logs.count_documents({})
    return {
        "datasets": [{"id": d["dataset_id"], "status": d.get("status"), "enabled": d.get("enabled")} for d in ds],
        "cnaes_active": sum(1 for c in cnaes if c.get("enabled")),
        "cnaes_total": len(cnaes),
        "audit_entries": audits,
    }


@router.get("/version")
async def registry_version():
    return {"registry_version": "1.0", "schema_version": "1.0.0"}


# ══════════════════════════════════════════
# INTERNALS
# ══════════════════════════════════════════

async def _audit(action: str, entity_id: str, user: dict, extra: dict = None):
    await db.registry_audit_logs.insert_one({
        "log_id": new_id(), "action": action, "entity_id": entity_id,
        "performed_by": user.get("email", user.get("id")),
        "timestamp": now_iso(), "extra": extra,
    })


async def _seed_datasets():
    """Seed default dataset registry from known providers."""
    now = now_iso()
    defaults = [
        {"dataset_id": "ine_iass", "provider": "INE", "dataset_type": "iass",
         "name": "IASS — Indicadores de Actividad del Sector Servicios",
         "description": "Evolucion de cifra de negocios, empleo y variaciones sectoriales",
         "supported_metrics": ["index", "yoy_change", "mom_change", "ytd_change"],
         "supported_cnaes": ["73"]},
        {"dataset_id": "ine_structural", "provider": "INE", "dataset_type": "structural",
         "name": "Estadistica Estructural de Empresas: Servicios",
         "description": "Ingresos agregados, personal ocupado, productividad sectorial",
         "supported_metrics": ["revenue", "employees", "productivity"],
         "supported_cnaes": []},
        {"dataset_id": "ine_ipc", "provider": "INE", "dataset_type": "ipc",
         "name": "IPC — Indice de Precios al Consumo",
         "description": "Indice general y variaciones para deflactar crecimiento nominal",
         "supported_metrics": ["price_index", "yoy_change"],
         "supported_cnaes": []},
        {"dataset_id": "ine_dirce", "provider": "INE", "dataset_type": "dirce",
         "name": "DIRCE — Empresas activas por CNAE y territorio",
         "description": "Numero de empresas activas por CNAE, territorio y tramo de empleados",
         "supported_metrics": ["company_count", "by_size", "by_territory"],
         "supported_cnaes": []},
        {"dataset_id": "borme_events", "provider": "BORME", "dataset_type": "borme",
         "name": "BORME — Actos mercantiles",
         "description": "Eventos registrales: fusiones, adquisiciones, constituciones, nombramientos",
         "supported_metrics": ["ma_events", "constitutions", "appointments"],
         "supported_cnaes": []},
        {"dataset_id": "iberinform_companies", "provider": "Iberinform", "dataset_type": "iberinform",
         "name": "Iberinform — Dataset empresarial",
         "description": "Datos financieros, empleados, CNAE, provincia, actividad",
         "supported_metrics": ["revenue", "ebitda", "employees", "margin"],
         "supported_cnaes": []},
    ]
    for d in defaults:
        existing = await db.provider_datasets.find_one({"dataset_id": d["dataset_id"]})
        if not existing:
            await db.provider_datasets.insert_one({
                **d, "status": "active", "enabled": True, "visible_in_valuo": True,
                "tables": [], "snapshot_enabled": True, "publication_enabled": True,
                "last_sync_at": None, "schema_version": "1.0", "contract_version": "1.0",
                "created_at": now, "updated_at": now,
            })
