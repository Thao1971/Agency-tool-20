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

FULL INGESTION (2026-07-24, decisión de Daniel "guardar TODO, no tirar nada"):
- Datos_BALANCES.tab: ahora se guarda el EAV COMPLETO (~500 partidas por empresa-año),
  no solo las 6 canónicas. Habilita ratios propios antes N/D sin cambiar los motores.
- Datos_RATIOS.tab: los 31 ratios precalculados de Iberinform -> `norm_financials.ratios`
  (fusionados en el mismo doc empresa-año). Se guardan todos; la curación de exposición
  en documentos está en memory/IBERINFORM_RATIOS_PRIORITY.md.
- Datos_SUCURSALES.tab / Datos_OTRAS_DIRECCIONES.tab -> `norm_company.branches` /
  `norm_company.alt_addresses` (fila cruda íntegra, nada se descarta).
Los nombres exactos de columna de los .tab de RATIOS/SUCURSALES/OTRAS_DIRECCIONES no
están en el fixture de muestra (solo el CSV Valu8); sus loaders resuelven columnas de
forma tolerante (`_resolve_col`) y registran error en el manifiesto si no las encuentran.
VALIDAR contra la primera entrega real.
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


# ── BALANCES → norm_financials (EAV pivot, FULL: every balance/P&L/cash-flow line) ──
async def ingest_balances_file(path: str, source_version: str, job_id: str, basis: str = "individual") -> Dict:
    man = _manifest_base(path, source_version, job_id, "norm_financials")
    up = BulkUpserter(db.norm_financials)
    rows = 0
    # (cif_normalized, year) -> {account_code: value}. We keep the FULL EAV — every
    # line item the file carries (~500 balance/P&L/cash-flow codes per company-year),
    # NOT just the 6 canonical ones. Rationale (Daniel, 2026-07-24): the source is
    # knowledge, nothing is discarded; storing raw is cheap (a per-doc code→value map)
    # and it lets the engines derive ratios that were N/D before (gross margin, liquidity,
    # interest coverage, financial debt…) with no engine change — `metrics.py` already
    # reads those extra codes; they were simply never stored. `derive_metrics()` still
    # reads its 6 canonical codes from the same full map for the summary fields.
    acc: Dict[Tuple[str, int], Dict[str, float]] = defaultdict(dict)
    cif_by_norm: Dict[str, str] = {}

    for r in _stream_tab_rows(path):
        rows += 1
        cif = _s(r, "REG_NUMBER")
        code = _s(r, "BALANCE_SHEET_ITEM")
        if not cif or not code:
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


async def _fail_manifest(man: Dict, error: str) -> None:
    """Persist a manifest as FAILED (never masked as completed — `_finish_manifest`
    always sets status=completed, so error paths must write their own record)."""
    man.update({"rows": 0, "status": "error", "error": error, "finished_at": now_iso()})
    await db.raw_ingestion_manifest.insert_one(man)


def _resolve_col(fieldnames, candidates) -> Optional[str]:
    """Find the first present column among `candidates` (case-insensitive, ignoring
    spaces/underscores). Returns the real field name or None. Used because the exact
    `.tab` headers for the RATIOS / branch files are not in our sample fixture and
    must be resolved tolerantly against the first real delivery."""
    norm = {str(f).strip().lower().replace(" ", "").replace("_", ""): f for f in (fieldnames or [])}
    for c in candidates:
        k = c.lower().replace(" ", "").replace("_", "")
        if k in norm:
            return norm[k]
    return None


# ── RATIOS → norm_financials.ratios (merge into the same company-year doc) ──
async def ingest_ratios_file(path: str, source_version: str, job_id: str, basis: str = "individual") -> Dict:
    """Ingest Datos_RATIOS.tab — Iberinform's 31 precomputed ratios per company-year —
    merging them into the matching norm_financials document as a `ratios` map
    (code -> value). Stores ALL ratios raw (curation to 28 for documents is a read-layer
    concern, see memory/IBERINFORM_RATIOS_PRIORITY.md). Column names are resolved
    tolerantly (see `_resolve_col`) and asserted; if the code column can't be found the
    manifest records an error rather than silently ingesting nothing."""
    man = _manifest_base(path, source_version, job_id, "norm_financials")
    up = BulkUpserter(db.norm_financials)
    rows = 0

    # peek header
    enc = detect_encoding(path)
    with open(path, encoding=enc, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames
    col_cif = _resolve_col(fields, ["REG_NUMBER", "NIF", "ES_NIF"])
    col_code = _resolve_col(fields, ["RATIO_ITEM", "RATIO_CODE", "RATIO_ID", "RATIO", "ES_Account_number"])
    col_year = _resolve_col(fields, ["RATIO_YEAR", "YEAR", "BALANCE_SHEET_YEAR", "Year"])
    col_val = _resolve_col(fields, ["RATIO_VALUE", "RATIO_ITEM_VALUE", "VALUE", "AMOUNT", "Amount_Eur"])
    if not (col_cif and col_code and col_val):
        msg = (f"No se pudieron resolver columnas de RATIOS (cif={col_cif}, code={col_code}, "
               f"year={col_year}, value={col_val}); cabecera real: {fields}")
        await _fail_manifest(man, msg)
        return {"file": man["file_name"], "rows": 0, "error": msg}

    ratios_by: Dict[Tuple[str, Optional[int]], Dict[str, float]] = defaultdict(dict)
    cif_by_norm: Dict[str, str] = {}
    for r in _stream_tab_rows(path):
        rows += 1
        cif = _s(r, col_cif)
        code = _s(r, col_code)
        cifn = normalize_cif(cif)
        if not cifn or not code:
            continue
        year = _int(r.get(col_year)) if col_year else None
        val = parse_amount(r.get(col_val))
        if val is None:
            continue
        cif_by_norm[cifn] = cif
        ratios_by[(cifn, year)][code] = val

    now = now_iso()
    for (cifn, year), ratios in ratios_by.items():
        # merge into the company-year doc (created by balances); upsert is safe either way
        up.upsert({"cif_normalized": cifn, "year": year, "basis": basis},
                  {"cif_normalized": cifn, "cif": cif_by_norm.get(cifn), "year": year, "basis": basis,
                   "ratios": ratios, "ratios_source": "iberinform", "source_version": source_version,
                   "source_file_id": man["source_file_id"], "ingestion_job_id": job_id,
                   "pipeline_version": PIPELINE_VERSION, "updated_at": now})
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, "company_years": len(ratios_by),
            "columns": {"cif": col_cif, "code": col_code, "year": col_year, "value": col_val}, **up.stats()}


# ── SUCURSALES / OTRAS_DIRECCIONES → norm_company.branches / alt_addresses ──
async def ingest_addresses_file(path: str, source_version: str, job_id: str,
                                field: str = "branches") -> Dict:
    """Ingest branch / alternate-address rows and attach them to the company as a list
    (`branches` or `alt_addresses`). Stores the whole row raw so nothing is lost; the
    exact `.tab` columns are resolved tolerantly against the first real delivery."""
    man = _manifest_base(path, source_version, job_id, "norm_company")
    up = BulkUpserter(db.norm_company)
    rows = 0
    enc = detect_encoding(path)
    with open(path, encoding=enc, errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = reader.fieldnames
    col_cif = _resolve_col(fields, ["REG_NUMBER", "NIF", "ES_NIF"])
    if not col_cif:
        msg = f"No se pudo resolver REG_NUMBER; cabecera: {fields}"
        await _fail_manifest(man, msg)
        return {"file": man["file_name"], "rows": 0, "error": msg}

    by_cif: Dict[str, list] = defaultdict(list)
    for r in _stream_tab_rows(path):
        rows += 1
        cifn = normalize_cif(r.get(col_cif))
        if not cifn:
            continue
        # keep the full row raw (minus the cif key), nothing discarded
        by_cif[cifn].append({k: (v.strip() if isinstance(v, str) else v)
                             for k, v in r.items() if k != col_cif and v not in (None, "")})

    now = now_iso()
    for cifn, items in by_cif.items():
        up.upsert({"cif_normalized": cifn},
                  {"cif_normalized": cifn, field: items, f"{field}_count": len(items),
                   "updated_at": now}, )
        await up.maybe_flush()
    await up.flush()
    await _finish_manifest(man, rows, up.stats())
    return {"file": man["file_name"], "rows": rows, "companies": len(by_cif), "field": field, **up.stats()}


# ── Orchestrator ─────────────────────────────────────────────────────
_FILE_MAP = {
    "Datos_GENERALES.tab": ("generales", None),
    "Datos_BALANCES.tab": ("balances", None),
    "Datos_ACCIONISTAS.tab": ("accionistas", None),
    "Datos_PARTICIPADAS.tab": ("participadas", None),
    "Datos_ORG_SOCIALES.tab": ("officers", None),
    "Datos_RESTO_ORG_SOCIALES.tab": ("officers", None),
    "Datos_APODERADOS.tab": ("officers", None),
    "Datos_RATIOS.tab": ("ratios", None),
    "Datos_SUCURSALES.tab": ("sucursales", None),
    "Datos_OTRAS_DIRECCIONES.tab": ("otras_direcciones", None),
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
    # RATIOS after BALANCES so it merges into the existing company-year documents.
    if "Datos_RATIOS.tab" in present:
        results.append(await ingest_ratios_file(present["Datos_RATIOS.tab"], source_version, job_id))
    if "Datos_SUCURSALES.tab" in present:
        results.append(await ingest_addresses_file(present["Datos_SUCURSALES.tab"], source_version, job_id, field="branches"))
    if "Datos_OTRAS_DIRECCIONES.tab" in present:
        results.append(await ingest_addresses_file(present["Datos_OTRAS_DIRECCIONES.tab"], source_version, job_id, field="alt_addresses"))

    return {"ingestion_job_id": job_id, "source_version": source_version, "files": results}
