"""Ingestión real desde fuentes públicas españolas.

Cada función baja, parsea y persiste datos reales en su colección correspondiente.
Sin datos sintéticos. Todos los registros llevan `source_url` + `ingested_at`
para garantizar trazabilidad.

NOTA OPERATIVA: estas funciones contactan servicios externos. Si el contenedor
no tiene acceso de salida o el dataset upstream cambia su esquema, devolverán
`{"status": "error", "reason": "..."}` sin escribir nada — explícitamente NO se
permiten fallbacks sintéticos.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Dict

import httpx

from database import db

logger = logging.getLogger(__name__)

UA = "Intelligence-Engine/1.0 (datos publicos espana)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_cif(cif: str) -> str:
    return (cif or "").upper().replace("-", "").replace(" ", "").strip()


# ─── Fuente 8: Ayudas y Subvenciones Públicas ────────────────────────────────
# Endpoint REST real (SNPSAP/BDNS): /bdnstrans/api/concesiones/busqueda
# Devuelve páginas {"content": [...], "totalElements": N, "last": bool}
async def ingest_ayudas_subvenciones(year: int | None = None, limit: int = 1000) -> Dict:
    """Ingesta de la Base Nacional de Subvenciones (BDNS / SNPSAP).

    API pública JSON sin autenticación. Trae concesiones reales (beneficiario,
    importe, convocatoria, organismo, fecha). Idempotente vía `concession_id`.
    """
    year = year or datetime.now(timezone.utc).year
    base = "https://www.infosubvenciones.es/bdnstrans/api/concesiones/busqueda"
    page_size = min(limit, 500)

    inserted = 0
    errors = 0
    try:
        await db.ayudas_subvenciones_publicas.create_index("concession_id", unique=True)
        await db.ayudas_subvenciones_publicas.create_index("cif_normalized")
    except Exception:
        pass

    import re
    cif_pat = re.compile(r"\b([A-Z]\d{7}[0-9A-Z]|\d{8}[A-Z])\b")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Intelligence-Engine/1.0)", "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as client:
        page = 0
        while inserted < limit:
            params = {
                "vpd": "GE", "pageSize": page_size, "page": page,
                "order": "fechaConcesion", "direccion": "desc",
                "fechaDesde": f"01/01/{year}",
            }
            try:
                r = await client.get(base, params=params)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                if inserted == 0:
                    return {"status": "error", "source": "bdns", "reason": str(e)[:200]}
                break

            items = data.get("content") or []
            if not items:
                break

            for it in items:
                if inserted >= limit:
                    break
                beneficiario = (it.get("beneficiario") or "").strip()
                cif_match = cif_pat.search(beneficiario)
                doc = {
                    "concession_id": str(it.get("id") or it.get("codConcesion") or ""),
                    "cif_normalized": _norm_cif(cif_match.group(1)) if cif_match else "",
                    "beneficiary_name": beneficiario,
                    "amount_eur": float(it.get("importe") or 0),
                    "program": it.get("convocatoria") or "",
                    "instrument": (it.get("instrumento") or "").strip(),
                    "organism": it.get("nivel3") or it.get("nivel2") or "",
                    "admin_region": it.get("nivel2") or "",
                    "admin_level": it.get("nivel1") or "",
                    "granted_date": it.get("fechaConcesion"),
                    "source": "BDNS",
                    "source_url": it.get("urlBR") or "https://www.infosubvenciones.es",
                    "raw": it,
                    "ingested_at": _now(),
                }
                if not doc["concession_id"]:
                    continue
                try:
                    await db.ayudas_subvenciones_publicas.update_one(
                        {"concession_id": doc["concession_id"]},
                        {"$set": doc}, upsert=True,
                    )
                    inserted += 1
                except Exception:
                    errors += 1

            if data.get("last") is True:
                break
            page += 1

    return {"status": "ok", "source": "bdns", "year": year,
            "inserted": inserted, "errors": errors,
            "total_in_collection": await db.ayudas_subvenciones_publicas.count_documents({})}


# ─── Fuente 9: Estadísticas de Empleo ────────────────────────────────────────
# SEPE Open Data + INE API (datos de paro registrado y afiliación por CNAE/provincia)
# https://datos.gob.es/es/catalogo/ea0021425-paro-registrado-por-municipios
# INE API: https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/
async def ingest_estadisticas_empleo() -> Dict:
    """Tasa de paro por CCAA — tabla INE 4247 (Tasas por sexo y comunidad autónoma).

    API JSON pública del INE. Carga el último periodo disponible.
    """
    table = "4247"  # Tasas de paro por CCAA
    url = f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table}?nult=4"

    try:
        await db.estadisticas_empleo.create_index([("ccaa", 1), ("period", -1)], unique=False)
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            series = r.json()
        except Exception as e:
            return {"status": "error", "source": "ine_4247", "reason": str(e)[:200]}

    inserted = 0
    for s in series:
        ccaa = (s.get("Nombre") or "").split(".")[0].strip()
        for d in s.get("Data") or []:
            if d.get("Valor") is None:
                continue
            doc = {
                "ccaa": ccaa,
                "period": f"{d.get('Anyo')}-T{d.get('T3_Periodo','')}".strip("-T"),
                "unemployment_rate": float(d["Valor"]),
                "source": "INE-4247",
                "source_url": url,
                "ingested_at": _now(),
            }
            await db.estadisticas_empleo.update_one(
                {"ccaa": doc["ccaa"], "period": doc["period"]},
                {"$set": doc}, upsert=True,
            )
            inserted += 1
    return {"status": "ok", "source": "ine_4247",
            "inserted": inserted,
            "total_in_collection": await db.estadisticas_empleo.count_documents({})}


# ─── Fuente 10: Estadísticas Territoriales ───────────────────────────────────
# INE API — Renta neta media por hogar por provincia (tabla 30896)
async def ingest_estadisticas_territoriales() -> Dict:
    """Renta media por hogar (provincias) — INE tabla 30896."""
    table = "30896"
    url = f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{table}?nult=2"

    try:
        await db.estadisticas_territoriales.create_index([("province", 1), ("year", -1)])
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": UA}) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            series = r.json()
        except Exception as e:
            return {"status": "error", "source": "ine_30896", "reason": str(e)[:200]}

    inserted = 0
    for s in series:
        province = (s.get("Nombre") or "").split(".")[0].strip()
        for d in s.get("Data") or []:
            if d.get("Valor") is None:
                continue
            doc = {
                "province": province,
                "year": int(d.get("Anyo") or 0),
                "average_income": float(d["Valor"]),
                "source": "INE-30896",
                "source_url": url,
                "ingested_at": _now(),
            }
            await db.estadisticas_territoriales.update_one(
                {"province": doc["province"], "year": doc["year"]},
                {"$set": doc}, upsert=True,
            )
            inserted += 1
    return {"status": "ok", "source": "ine_30896",
            "inserted": inserted,
            "total_in_collection": await db.estadisticas_territoriales.count_documents({})}
