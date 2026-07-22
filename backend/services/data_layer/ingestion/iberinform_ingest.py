"""Iberinform Valu8 ingestion — raw CSV (object-storage landing) → Normalized layer.

P0.7 + P0.1: streaming read, sort-merge EAV pivot to one financial doc per
(cif_normalized, year, basis), chunked bulk_write(ordered=False). Idempotent and
re-runnable. Trazabilidad: source_file_id + checksum + ingestion_job_id + lineage,
sin replicar el CSV bruto fila-a-fila en Mongo.
"""

import os
import re
import uuid
import logging
from typing import Dict, Optional

from database import db
from models import now_iso
from services.data_layer.normalize import (
    normalize_cif, name_key, build_aliases, division_of, resolve_section,
    section_label, division_label,
)
from services.data_layer.ingestion.csv_stream import stream_rows, count_rows, file_stats
from services.data_layer.ingestion.account_map import parse_amount, derive_metrics
from services.data_layer.ingestion.bulk import BulkUpserter

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "ingest-v1"
_CIF_RE = re.compile(r"^[A-Z]\d{7}[A-Z0-9]$|^\d{8}[A-Z]$", re.I)


def _int(v) -> Optional[int]:
    f = parse_amount(v)
    return int(f) if f is not None else None


def _looks_like_cif(v: Optional[str]) -> bool:
    return bool(v and _CIF_RE.match(v.strip()))


async def ensure_indexes() -> None:
    await db.norm_company.create_index("cif_normalized", unique=True)
    await db.norm_company.create_index("name_key")
    await db.norm_financials.create_index(
        [("cif_normalized", 1), ("year", 1), ("basis", 1)], unique=True)
    await db.norm_ownership.create_index(
        [("src_cif", 1), ("counterparty_key", 1), ("relationship_type", 1), ("year", 1)], unique=True)
    await db.norm_ownership.create_index("counterparty_cif")
    await db.norm_officers.create_index(
        [("cif_normalized", 1), ("person_key", 1), ("role", 1), ("appointment_date", 1)], unique=True)
    await db.raw_ingestion_manifest.create_index("source_file_id", unique=True)
    await db.raw_ingestion_manifest.create_index("checksum")


def _manifest_base(path: str, source_version: str, job_id: str, target: str) -> Dict:
    checksum, nbytes = file_stats(path)
    return {
        "source_file_id": str(uuid.uuid4()),
        "file_name": os.path.basename(path),
        "source_version": source_version,
        "checksum": checksum,
        "bytes": nbytes,
        "ingestion_job_id": job_id,
        "target_collection": target,
        "lineage": {"layer": "raw->normalized", "produces": target},
        "pipeline_version": PIPELINE_VERSION,
        "started_at": now_iso(),
        "status": "running",
    }


async def _finish_manifest(man: Dict, rows: int, stats: Dict) -> None:
    man.update({"rows": rows, "status": "completed", "finished_at": now_iso(), **stats})
    await db.raw_ingestion_manifest.insert_one(man)


# ── Company (wide master) ─────────────────────────────────────────────
async def ingest_company_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_company")
    up = BulkUpserter(db.norm_company)
    rows = 0
    for r in stream_rows(path):
        rows += 1
        cif = (r.get("CIF") or "").strip()
        cifn = normalize_cif(cif)
        if not cifn:
            continue
        cnae = (r.get("CNAE") or "").strip() or None
        div = division_of(cnae)
        doc = {
            "cif_normalized": cifn, "cif": cif, "iberinform_id": (r.get("ID_FIRMA") or "").strip(),
            "legal_name": (r.get("DENOMINACION") or "").strip() or None,
            "commercial_name": (r.get("TITULO_COMERCIAL") or "").strip() or None,
            "sigla": (r.get("SIGLA") or "").strip() or None,
            "name_key": name_key(r.get("DENOMINACION")),
            "aliases": build_aliases(r.get("DENOMINACION"), r.get("TITULO_COMERCIAL"), r.get("SIGLA")),
            "cnae_code": cnae, "cnae_description": (r.get("DESCRIPCION_CNAE") or "").strip() or None,
            "cnae_division": div, "cnae_section": resolve_section(cnae),
            "web": (r.get("WEB") or "").strip() or None,
            "objeto_social": (r.get("OBJETO_SOCIAL") or "").strip() or None,
            "address": {
                "domicilio": (r.get("DOMICILIO") or "").strip() or None,
                "codigo_postal": (r.get("CODIGO_POSTAL") or "").strip() or None,
                "municipio": (r.get("MUNICIPIO") or "").strip() or None,
                "provincia": (r.get("PROVINCIA") or "").strip() or None,
                "pais": (r.get("PAIS") or "").strip() or None,
            },
            "employees_total": _int(r.get("TOTAL_EMPLEADOS")),
            "capital_social": parse_amount(r.get("CAPITAL_SOCIAL")),
            "sales": parse_amount(r.get("VENTAS")),
            "sit_mercantil": (r.get("SIT_MERCANTIL") or "").strip() or None,
            "audited": (r.get("AUDITADO") or "").strip() or None,
            "balance_model": (r.get("MODELO_BALANCE") or "").strip() or None,
            "last_balance_year": (r.get("ULT_EJERCICIO_BALANCE") or "").strip() or None,
            "fiscal_close_date": (r.get("FECHA_CIERRE_EJERCICIO") or "").strip() or None,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now_iso(), "dirty": True,
        }
        up.upsert({"cif_normalized": cifn}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, **up.stats()}


# ── Financial detail (EAV → pivot by company-year) ────────────────────
async def ingest_financial_file(path: str, basis: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_financials")
    up = BulkUpserter(db.norm_financials)
    rows = 0
    current_nif = None
    buf: Dict[str, Dict[str, float]] = {}  # year -> accounts

    async def _flush_company(nif: str, by_year: Dict[str, Dict[str, float]]):
        cifn = normalize_cif(nif)
        if not cifn:
            return
        for year, accounts in by_year.items():
            yr = _int(year)
            metrics = derive_metrics(accounts)
            doc = {
                "cif_normalized": cifn, "cif": nif, "year": yr, "basis": basis,
                "accounts": accounts, **metrics,
                "source": "iberinform", "source_version": source_version,
                "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
                "pipeline_version": PIPELINE_VERSION, "updated_at": now_iso(),
            }
            up.upsert({"cif_normalized": cifn, "year": yr, "basis": basis}, doc)
        await up.maybe_flush()

    for r in stream_rows(path):
        rows += 1
        nif = (r.get("ES_NIF") or "").strip()
        year = (r.get("Year") or "").strip()
        code = (r.get("ES_Account_number") or "").strip()
        amount = parse_amount(r.get("Amount_Eur"))
        if not nif or not code:
            continue
        if nif != current_nif and current_nif is not None:
            await _flush_company(current_nif, buf)
            buf = {}
        current_nif = nif
        buf.setdefault(year, {})[code] = amount
    if current_nif is not None:
        await _flush_company(current_nif, buf)
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, "basis": basis, **up.stats()}


# ── Ownership (Vinculaciones + Matriz Accionistas) ────────────────────
async def ingest_ownership_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_ownership")
    up = BulkUpserter(db.norm_ownership)
    rows = 0
    for r in stream_rows(path):
        rows += 1
        src = (r.get("ES_NIF") or "").strip()
        rtype = (r.get("ES_Account_ID") or "").strip().lower()
        dst_raw = (r.get("ES_Account_number") or "").strip()
        name = (r.get("ES_Account_Name") or "").strip() or None
        src_cif = normalize_cif(src)
        if not src_cif or not rtype:
            continue
        dst_cif = normalize_cif(dst_raw) if _looks_like_cif(dst_raw) else None
        counterparty_key = dst_cif or name_key(name) or "unknown"
        year = _int(r.get("Year"))
        doc = {
            "src_cif": src_cif, "counterparty_cif": dst_cif, "counterparty_key": counterparty_key,
            "counterparty_name": name, "counterparty_has_cif": bool(dst_cif),
            "relationship_type": rtype, "pct": parse_amount(r.get("Amount_Eur")), "year": year,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now_iso(),
        }
        up.upsert({"src_cif": src_cif, "counterparty_key": counterparty_key,
                   "relationship_type": rtype, "year": year}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, **up.stats()}


# ── Officers / company bodies (Org Social) ────────────────────────────
async def ingest_officers_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_officers")
    up = BulkUpserter(db.norm_officers)
    rows = 0
    for r in stream_rows(path):
        rows += 1
        cifn = normalize_cif((r.get("ES_NIF") or "").strip())
        role = (r.get("ES_Account_number") or "").strip() or None
        person = (r.get("ES_Account_Name") or "").strip() or None
        appt = (r.get("Appointment_Date") or "").strip() or ""
        pkey = name_key(person)
        if not cifn or not pkey or not role:
            continue
        doc = {
            "cif_normalized": cifn, "person_name": person, "person_key": pkey,
            "role": role, "appointment_date": appt, "year": _int(r.get("Year")),
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now_iso(),
        }
        up.upsert({"cif_normalized": cifn, "person_key": pkey, "role": role,
                   "appointment_date": appt}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, **up.stats()}


# ── Orchestrator ──────────────────────────────────────────────────────
def _classify(fname: str) -> Optional[tuple]:
    f = fname.lower()
    if not f.endswith(".csv"):
        return None
    if "company_data" in f:
        return ("company", None)
    if "financial_detail" in f:
        return ("financial", "consolidated" if "conso" in f else "individual")
    if "org_social" in f:
        return ("officers", None)
    if "vinculaciones" in f or "matriz_accionistas" in f:
        return ("ownership", None)
    return None


def list_ingestable(directory: str) -> list:
    """Sorted list of CSV filenames in `directory` recognized by the ingestor."""
    return [f for f in sorted(os.listdir(directory)) if _classify(f)]


async def ingest_file(path: str, source_version: str, job_id: str) -> Dict:
    """Dispatch a single CSV to its per-type ingestor (used by orchestrator + job handler)."""
    ftype, basis = _classify(os.path.basename(path))
    if ftype == "company":
        return await ingest_company_file(path, source_version, job_id)
    if ftype == "financial":
        return await ingest_financial_file(path, basis, source_version, job_id)
    if ftype == "ownership":
        return await ingest_ownership_file(path, source_version, job_id)
    if ftype == "officers":
        return await ingest_officers_file(path, source_version, job_id)
    raise ValueError(f"unrecognized file: {path}")


async def ingest_directory(directory: str, source_version: Optional[str] = None) -> Dict:
    """Ingest all Iberinform CSVs in a directory into the Normalized layer (one-shot)."""
    await ensure_indexes()
    job_id = str(uuid.uuid4())
    source_version = source_version or os.path.basename(directory.rstrip("/")).split("_")[0]
    results = [await ingest_file(os.path.join(directory, f), source_version, job_id)
               for f in list_ingestable(directory)]
    return {"ingestion_job_id": job_id, "source_version": source_version, "files": results}
