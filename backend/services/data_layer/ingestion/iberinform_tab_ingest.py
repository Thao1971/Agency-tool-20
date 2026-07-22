"""Iberinform "translated" export ingestion — tab-separated multi-file delivery → Normalized layer.

Daniel's real 25,000-company sample (2026-07) arrived in a different shape than the
original "Valu8" CSV format `iberinform_ingest.py` was built against: 10 tab-separated
files (`Datos_GENERALES.tab`, `Datos_BALANCES.tab`, `Datos_ACCIONISTAS.tab`,
`Datos_PARTICIPADAS.tab`, `Datos_ORG_SOCIALES.tab`, `Datos_RESTO_ORG_SOCIALES.tab`,
`Datos_APODERADOS.tab`, `Datos_RATIOS.tab`, `Datos_SUCURSALES.tab`,
`Datos_OTRAS_DIRECCIONES.tab`), English field names, tab delimiter, CRLF line endings,
Latin-1 encoded (verified: accented names decode as \\xf1/\\xd1, not UTF-8).

Verified against `Diccionario_Datos_Financial_Info.pdf` + `Financial Info Translated
V2.xlsx` (both supplied alongside the sample) before writing this:
- REG_NUMBER is the NIF/CIF directly (e.g. "A0051199H") — same identity key as the
  existing pipeline's `cif_normalized`.
- Datos_BALANCES.tab's BALANCE_SHEET_ITEM codes are the SAME numbering as
  `account_map.ACCOUNT_MAP` (10000=total_assets, 20000=equity, 40100=revenue,
  40800=depreciation, 49100=operating_income, 49500=net_income) — confirmed against
  the "Financial Statements" crosswalk sheet (924 rows) in the translated workbook.
  `derive_metrics()` is reused as-is, no new account map needed.
- Datos_ACCIONISTAS.tab (who owns REG_NUMBER) and Datos_PARTICIPADAS.tab (who
  REG_NUMBER owns) map onto `norm_ownership`'s existing "shareholder" / "investee_co"
  relationship types (see `ownership_graph.py TYPE_MAP`) — same direction semantics,
  just different source column names. GENERALES.PARENT_COMPANY_REG_NUMBER supplies a
  third edge type, "parent_co", not present as a separate file in this delivery.
- Datos_ORG_SOCIALES / Datos_RESTO_ORG_SOCIALES / Datos_APODERADOS share an identical
  column layout and all three feed `norm_officers` (board members, other corporate
  roles, and proxy holders respectively — the distinction lives in CORPORATE_BODY_CODE
  /POSITION, not in a separate schema).

Writes to the EXACT SAME target collections (`norm_company`, `norm_financials`,
`norm_ownership`, `norm_officers`) as `iberinform_ingest.py`, with the same document
shape, so the existing, unmodified `rebuild_master()` / `rebuild_ownership_graph()`
(services/data_layer/master/*) pick this data up with no changes on their end.

Deliberately NOT reused in this MVP pass (documented, not silently dropped):
Datos_RATIOS.tab (924-code crosswalk covers ratios too, but derive_metrics() only
needs the 6 core accounts — ratios stored raw would need a new `norm_ratios`
collection, no current consumer), Datos_SUCURSALES.tab / Datos_OTRAS_DIRECCIONES.tab
(branch/alternate addresses, no current consumer).
"""

import csv
import logging
import os
import uuid
from collections import defaultdict
from typing import Dict, Optional, Tuple

from database import db
from models import now_iso
from services.data_layer.normalize import normalize_cif, name_key, build_aliases, division_of, resolve_section
from services.data_layer.ingestion.csv_stream import detect_encoding, file_stats
from services.data_layer.ingestion.account_map import parse_amount, derive_metrics, ACCOUNT_MAP
from services.data_layer.ingestion.bulk import BulkUpserter
from services.data_layer.ingestion.iberinform_ingest import _manifest_base, _finish_manifest, ensure_indexes

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "ingest-tab-v1"

# REG_NUMBER-based ownership sources, see module docstring for direction reasoning.
_ACCOUNT_CODES = set(ACCOUNT_MAP.keys())


def _stream_tab_rows(path: str):
    enc = detect_encoding(path)
    with open(path, encoding=enc, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            yield row


def _s(row: Dict, key: str) -> str:
    v = row.get(key)
    return str(v).strip() if v is not None else ""


def _int(v: str) -> Optional[int]:
    f = parse_amount(v)
    return int(f) if f is not None else None


# ── GENERALES → norm_company (+ parent_co ownership edge) ──────────────
async def ingest_generales_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_company")
    up_company = BulkUpserter(db.norm_company)
    up_own = BulkUpserter(db.norm_ownership)
    rows = 0
    parent_edges = 0
    now = now_iso()

    for r in _stream_tab_rows(path):
        rows += 1
        cif = _s(r, "REG_NUMBER")
        cifn = normalize_cif(cif)
        if not cifn:
            continue
        cnae = _s(r, "ACTIVITY_CODE") or None
        street = " ".join(x for x in [_s(r, "STREET_TYPE"), _s(r, "STREET_NAME"), _s(r, "STREET_NUMBER")] if x) or None
        doc = {
            "cif_normalized": cifn, "cif": cif,
            "legal_name": _s(r, "COMPANY_NAME") or None,
            "commercial_name": _s(r, "TRADE_NAME") or None,
            "sigla": _s(r, "SHORT_ES") or None,
            "name_key": name_key(r.get("COMPANY_NAME")),
            "aliases": build_aliases(r.get("COMPANY_NAME"), r.get("TRADE_NAME")),
            "cnae_code": cnae, "cnae_description": _s(r, "ACTIVITY_DESCRIPTION") or None,
            "cnae_division": division_of(cnae), "cnae_section": resolve_section(cnae),
            "web": _s(r, "URL") or None,
            "objeto_social": _s(r, "CORPORATE_PURPOSE") or None,
            "address": {
                "domicilio": street,
                "codigo_postal": _s(r, "ZIP_CODE") or None,
                "municipio": _s(r, "TOWN") or None,
                "provincia": _s(r, "PROVINCE") or None,
                "pais": "ESPANA",
            },
            "employees_total": _int(r.get("EMPLOYEES")),
            "capital_social": None,
            "sales": None,  # real revenue comes from BALANCES (40100), not duplicated here
            "sit_mercantil": _s(r, "TRADING_STATUS") or _s(r, "CONFIRMED_STATUS") or None,
            "audited": _s(r, "INDIC_INDIVID_BALANC_SHEET_AUDIT") or None,
            "balance_model": None,
            "last_balance_year": _s(r, "INDIV_LATEST_FILED_ACCOUNTS_YEAR") or None,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now_iso(), "dirty": True,
        }
        up_company.upsert({"cif_normalized": cifn}, doc)

        parent_cif_raw = _s(r, "PARENT_COMPANY_REG_NUMBER")
        parent_name = _s(r, "PARENT_COMPANY_NAME")
        if parent_cif_raw or parent_name:
            parent_cif = normalize_cif(parent_cif_raw) if parent_cif_raw else None
            ckey = parent_cif or name_key(parent_name) or "unknown"
            odoc = {
                "src_cif": cifn, "counterparty_cif": parent_cif, "counterparty_key": ckey,
                "counterparty_name": parent_name or None, "counterparty_has_cif": bool(parent_cif),
                "relationship_type": "parent_co", "pct": None, "year": None,
                "source": "iberinform", "source_version": source_version,
                "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
                "pipeline_version": PIPELINE_VERSION, "updated_at": now,
            }
            up_own.upsert({"src_cif": cifn, "counterparty_key": ckey,
                          "relationship_type": "parent_co", "year": None}, odoc)
            parent_edges += 1

        await up_company.maybe_flush()
        await up_own.maybe_flush()

    await up_company.flush()
    await up_own.flush()
    await _finish_manifest(man, rows, up_company.stats())
    return {"file": man["file_name"], "rows": rows, "parent_edges": parent_edges, **up_company.stats()}


# ── BALANCES → norm_financials (EAV pivot, filtered to the 6 mapped account codes) ──
async def ingest_balances_file(path: str, source_version: str, job_id: str, basis: str = "individual") -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_financials")
    up = BulkUpserter(db.norm_financials)
    rows = 0
    # (cif_normalized, year) -> {account_code: value}. Only the 6 codes in ACCOUNT_MAP
    # are kept — the file carries ~900 possible line items per company-year, but
    # derive_metrics() only ever reads these 6, so there is no correctness reason
    # (and real memory reasons not to) keep the rest for 25k companies x N years.
    acc: Dict[Tuple[str, int], Dict[str, float]] = defaultdict(dict)
    cif_by_norm: Dict[str, str] = {}

    for r in _stream_tab_rows(path):
        rows += 1
        cif = _s(r, "REG_NUMBER")
        code = _s(r, "BALANCE_SHEET_ITEM")
        if not cif or code not in _ACCOUNT_CODES:
            continue
        cifn = normalize_cif(cif)
        if not cifn:
            continue
        year = _int(r.get("BALANCE_SHEET_YEAR"))
        val = parse_amount(r.get("BALANCE_SHEET_ITEM_VALUE"))
        if year is None or val is None:
            continue
        cif_by_norm[cifn] = cif
        acc[(cifn, year)][code] = val

    now = now_iso()
    for (cifn, year), accounts in acc.items():
        metrics = derive_metrics(accounts)
        doc = {
            "cif_normalized": cifn, "cif": cif_by_norm.get(cifn), "year": year, "basis": basis,
            "accounts": accounts, **metrics,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now,
        }
        up.upsert({"cif_normalized": cifn, "year": year, "basis": basis}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, "company_years": len(acc), "basis": basis, **up.stats()}


# ── ACCIONISTAS → norm_ownership (relationship_type="shareholder") ─────
async def ingest_accionistas_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_ownership")
    up = BulkUpserter(db.norm_ownership)
    rows = 0
    now = now_iso()
    for r in _stream_tab_rows(path):
        rows += 1
        src_cif = normalize_cif(r.get("REG_NUMBER"))
        if not src_cif:
            continue
        holder_cif_raw = _s(r, "SHAREHOLDER_FULL_REG_NUMBER")
        holder_name = _s(r, "SHAREHOLDER_NAME") or None
        holder_cif = normalize_cif(holder_cif_raw) if holder_cif_raw else None
        ckey = holder_cif or name_key(holder_name) or "unknown"
        pct = parse_amount(r.get("SHAREHOLDER_SHARE_PERCENTAGE"))
        doc = {
            "src_cif": src_cif, "counterparty_cif": holder_cif, "counterparty_key": ckey,
            "counterparty_name": holder_name, "counterparty_has_cif": bool(holder_cif),
            "relationship_type": "shareholder", "pct": pct, "year": None,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now,
        }
        up.upsert({"src_cif": src_cif, "counterparty_key": ckey,
                   "relationship_type": "shareholder", "year": None}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, **up.stats()}


# ── PARTICIPADAS → norm_ownership (relationship_type="investee_co") ────
async def ingest_participadas_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_ownership")
    up = BulkUpserter(db.norm_ownership)
    rows = 0
    now = now_iso()
    for r in _stream_tab_rows(path):
        rows += 1
        src_cif = normalize_cif(r.get("REG_NUMBER"))
        if not src_cif:
            continue
        sub_cif_raw = _s(r, "SUBSIDIARY_FULL_REG_NUMBER")
        sub_name = _s(r, "SUBSIDIARY_COMPANY_NAME") or None
        sub_cif = normalize_cif(sub_cif_raw) if sub_cif_raw else None
        ckey = sub_cif or name_key(sub_name) or "unknown"
        pct = parse_amount(r.get("TOTAL_INTEREST_PERCENTAGE"))
        doc = {
            "src_cif": src_cif, "counterparty_cif": sub_cif, "counterparty_key": ckey,
            "counterparty_name": sub_name, "counterparty_has_cif": bool(sub_cif),
            "relationship_type": "investee_co", "pct": pct, "year": None,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now,
        }
        up.upsert({"src_cif": src_cif, "counterparty_key": ckey,
                   "relationship_type": "investee_co", "year": None}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, **up.stats()}


# ── ORG_SOCIALES / RESTO_ORG_SOCIALES / APODERADOS → norm_officers ─────
async def ingest_officers_file(path: str, source_version: str, job_id: str) -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_officers")
    up = BulkUpserter(db.norm_officers)
    rows = 0
    now = now_iso()
    for r in _stream_tab_rows(path):
        rows += 1
        cifn = normalize_cif(r.get("REG_NUMBER"))
        role = _s(r, "CORPORATE_BODY_POSITION") or None
        person = _s(r, "CORPORATE_BODY_NAME") or None
        appt = _s(r, "CORPORATE_BODY_APPOINTMENT_DATE") or ""
        pkey = name_key(person)
        if not cifn or not pkey or not role:
            continue
        doc = {
            "cif_normalized": cifn, "person_name": person, "person_key": pkey,
            "role": role, "appointment_date": appt, "year": None,
            "source": "iberinform", "source_version": source_version,
            "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
            "pipeline_version": PIPELINE_VERSION, "updated_at": now,
        }
        up.upsert({"cif_normalized": cifn, "person_key": pkey, "role": role,
                   "appointment_date": appt}, doc)
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, **up.stats()}


# ── Orchestrator ─────────────────────────────────────────────────────
_FILE_MAP = {
    "Datos_GENERALES.tab": ("generales", None),
    "Datos_BALANCES.tab": ("balances", None),
    "Datos_ACCIONISTAS.tab": ("accionistas", None),
    "Datos_PARTICIPADAS.tab": ("participadas", None),
    "Datos_ORG_SOCIALES.tab": ("officers", None),
    "Datos_RESTO_ORG_SOCIALES.tab": ("officers", None),
    "Datos_APODERADOS.tab": ("officers", None),
    # Deliberately not ingested in this pass — see module docstring.
    # "Datos_RATIOS.tab", "Datos_SUCURSALES.tab", "Datos_OTRAS_DIRECCIONES.tab"
}


def list_ingestable(directory: str) -> list:
    return [f for f in sorted(os.listdir(directory)) if f in _FILE_MAP]


async def ingest_tab_directory(directory: str, source_version: Optional[str] = None) -> Dict:
    """Ingest all recognized Datos_*.tab files in `directory` into the Normalized layer.

    Company file processed first (cheap and gives an early signal if REG_NUMBER
    parsing is off); order among the rest doesn't matter — all are independent
    upserts keyed by their own natural keys.
    """
    await ensure_indexes()
    job_id = str(uuid.uuid4())
    source_version = source_version or f"iberinform_tab_{uuid.uuid4().hex[:8]}"

    results = []
    present = {f: os.path.join(directory, f) for f in os.listdir(directory) if f in _FILE_MAP}

    if "Datos_GENERALES.tab" in present:
        results.append(await ingest_generales_file(present["Datos_GENERALES.tab"], source_version, job_id))
    if "Datos_BALANCES.tab" in present:
        results.append(await ingest_balances_file(present["Datos_BALANCES.tab"], source_version, job_id))
    if "Datos_ACCIONISTAS.tab" in present:
        results.append(await ingest_accionistas_file(present["Datos_ACCIONISTAS.tab"], source_version, job_id))
    if "Datos_PARTICIPADAS.tab" in present:
        results.append(await ingest_participadas_file(present["Datos_PARTICIPADAS.tab"], source_version, job_id))
    for fname in ("Datos_ORG_SOCIALES.tab", "Datos_RESTO_ORG_SOCIALES.tab", "Datos_APODERADOS.tab"):
        if fname in present:
            results.append(await ingest_officers_file(present[fname], source_version, job_id))

    return {"ingestion_job_id": job_id, "source_version": source_version, "files": results}
