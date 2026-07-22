"""INE Connector — Fetches data from Spain's National Statistics Institute (INE) API."""

import logging
import httpx
from typing import Optional, List, Dict
from database import db
from models import new_id, now_iso

logger = logging.getLogger(__name__)

BASE_URL = "https://servicios.ine.es/wstempus/js/ES"

# Key operations for advertising/services sector
KNOWN_OPERATIONS = {
    "iass": {"id": 31, "name": "Indicadores de Actividad del Sector Servicios"},
    "structural_services": {"id": 130, "name": "Estadistica Estructural de Empresas: Sector Servicios"},
    "price_indices": {"id": 14, "name": "Indices de Precios del Sector Servicios"},
    "labor_cost": {"id": 139, "name": "Encuesta Anual de Coste Laboral"},
    "service_production": {"id": 250, "name": "Indice de Produccion del Sector Servicios"},
}


async def get_available_operations() -> List[Dict]:
    """Fetch all available INE operations."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE_URL}/OPERACIONES_DISPONIBLES")
        r.raise_for_status()
        return r.json()


async def get_operation_tables(operation_id: int) -> List[Dict]:
    """Fetch tables for a given INE operation."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE_URL}/TABLAS_OPERACION/{operation_id}")
        r.raise_for_status()
        return r.json()


async def get_table_data(table_id: int, nult: Optional[int] = None, date: Optional[str] = None,
                          tip: str = "A", det: int = 2) -> List[Dict]:
    """Fetch data for a specific INE table."""
    params = {}
    if nult:
        params["nult"] = nult
    if date:
        params["date"] = date
    params["tip"] = tip
    params["det"] = det

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{BASE_URL}/DATOS_TABLA/{table_id}", params=params)
        r.raise_for_status()
        return r.json()


async def get_table_groups(table_id: int) -> List[Dict]:
    """Fetch group structure for a table."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE_URL}/GRUPOS_TABLA/{table_id}")
        r.raise_for_status()
        return r.json()


def normalize_ine_response(raw: List[Dict], table_id: int, dataset_type: str) -> List[Dict]:
    """Normalize INE API response into storable observations."""
    observations = []
    now = now_iso()

    # CNAE detection from series names
    CNAE_MAP = {
        "publicidad y estudios de mercado": "73",
        "actividades de publicidad": "731",
        "estudios de mercado": "732",
        "actividades inmobiliarias": "68",
        "actividades juridicas y de contabilidad": "69",
        "actividades de consultoria de gestion": "70",
        "arquitectura e ingenieria": "71",
        "investigacion y desarrollo": "72",
        "actividades veterinarias": "75",
        "programacion y emision de radio y television": "60",
        "cinematograficas": "59",
        "edicion": "58",
        "telecomunicaciones": "61",
        "programacion, consultoria y otras actividades": "62",
        "servicios de informacion": "63",
    }

    for series in raw:
        series_name = series.get("Nombre", "")
        series_code = series.get("COD", "")
        name_lower = series_name.lower()

        # Detect CNAE from series name
        cnae_code = None
        cnae_label = None
        for pattern, code in CNAE_MAP.items():
            if pattern in name_lower:
                cnae_code = code
                cnae_label = pattern.title()
                break

        # Extract metric type from name
        metric = None
        name_ascii = name_lower.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
        if ("indice" in name_ascii or "índice" in name_lower) and "variaci" not in name_ascii:
            metric = "index"
        elif "variacion anual" in name_ascii or "variación anual" in name_lower:
            metric = "yoy_change"
        elif "variacion mensual" in name_ascii or "variación mensual" in name_lower:
            metric = "mom_change"
        elif "variacion de la media" in name_ascii or "variación de la media" in name_lower:
            metric = "ytd_change"
        elif "ponderacion" in name_ascii:
            metric = "weight"
        elif "coeficiente" in name_ascii:
            metric = "cv"

        for dp in series.get("Data", []):
            if dp.get("Secreto"):
                continue

            observations.append({
                "observation_id": new_id(),
                "table_id": table_id,
                "dataset_type": dataset_type,
                "series_code": series_code,
                "series_name": series_name,
                "cnae_code": cnae_code,
                "cnae_label": cnae_label,
                "metric": metric,
                "year": dp.get("Anyo"),
                "period": dp.get("FK_Periodo"),
                "value": dp.get("Valor"),
                "unit": series.get("FK_Unidad"),
                "scale": series.get("FK_Escala"),
                "data_type": dp.get("FK_TipoDato"),
                "source_url": f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table_id}",
                "fetched_at": now,
            })

    return observations


async def sync_ine_table(table_id: int, dataset_type: str, cnae_scope: Optional[str] = None,
                          nult: int = 5) -> Dict:
    """Fetch, normalize, and store INE table data."""
    now = now_iso()
    sync_id = f"ine_sync_{new_id()[:8]}"

    try:
        raw = await get_table_data(table_id, nult=nult)
        observations = normalize_ine_response(raw, table_id, dataset_type)

        # Filter by CNAE scope if specified
        if cnae_scope:
            observations = [o for o in observations if o.get("cnae_code") and o["cnae_code"].startswith(cnae_scope)]

        # Upsert observations
        inserted = 0
        for obs in observations:
            existing = await db.ine_observations.find_one({
                "table_id": table_id, "series_code": obs["series_code"],
                "year": obs["year"], "period": obs["period"]
            })
            if existing:
                await db.ine_observations.update_one(
                    {"observation_id": existing["observation_id"]},
                    {"$set": {"value": obs["value"], "fetched_at": obs["fetched_at"]}}
                )
            else:
                await db.ine_observations.insert_one({**obs})
                inserted += 1

        # Log sync
        log = {
            "sync_id": sync_id, "provider": "ine", "table_id": table_id,
            "dataset_type": dataset_type, "cnae_scope": cnae_scope,
            "raw_series": len(raw), "observations_total": len(observations),
            "observations_inserted": inserted,
            "status": "completed", "error": None,
            "synced_at": now,
        }
        await db.ine_sync_logs.insert_one({**log})

        # Update provider status
        await db.data_provider_status.update_one(
            {"provider": "ine"},
            {"$set": {"status": "ok", "last_sync_at": now, "last_error": None,
                      "records_count": await db.ine_observations.count_documents({}),
                      "updated_at": now}},
            upsert=True
        )

        return {"sync_id": sync_id, "status": "completed", "series": len(raw),
                "observations": len(observations), "inserted": inserted}

    except Exception as e:
        logger.error(f"INE sync failed for table {table_id}: {e}")
        log = {
            "sync_id": sync_id, "provider": "ine", "table_id": table_id,
            "dataset_type": dataset_type, "status": "error", "error": str(e)[:500],
            "synced_at": now,
        }
        await db.ine_sync_logs.insert_one({**log})
        await db.data_provider_status.update_one(
            {"provider": "ine"},
            {"$set": {"status": "error", "last_error": str(e)[:200], "updated_at": now}},
            upsert=True
        )
        return {"sync_id": sync_id, "status": "error", "error": str(e)[:200]}
