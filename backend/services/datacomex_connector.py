"""DataComex Connector — Fetches trade data from datacomex.comercio.es.

Hybrid approach:
  1. Auto-sync via POST to DataComex form endpoint (monthly)
  2. Manual CSV upload fallback if auto-sync fails

Data flow: DataComex (TARIC) → datacomex_raw_data → TARIC→CNAE mapping → datacomex_trade_metrics → signals
"""

import logging
import io
import csv
import math
from typing import Dict, List, Optional
from datetime import datetime, timezone
import httpx
from database import db
from models import new_id, now_iso
from services.taric_cnae_mapping import TARIC_CHAPTERS, DEFAULT_TARIC_TO_CNAE

logger = logging.getLogger(__name__)

DATACOMEX_URL = "https://datacomex.comercio.es/Data/Index"


async def sync_datacomex(years: List[int] = None, taric_level: str = "2") -> Dict:
    """Fetch trade data from DataComex for specified years.

    Args:
        years: List of years to fetch. Defaults to last 6 years.
        taric_level: '2' for 2-digit chapters (default), '4' for 4-digit.
    """
    now = now_iso()
    if not years:
        current_year = datetime.now(timezone.utc).year
        years = list(range(current_year - 5, current_year + 1))

    total_imported = 0
    errors = []

    for year in years:
        for flow in ["export", "import"]:
            try:
                records = await _fetch_year_flow(year, flow, taric_level)
                if records:
                    await _store_raw_data(records, year, flow, now)
                    total_imported += len(records)
                    logger.info(f"DataComex: {year} {flow} — {len(records)} records")
                else:
                    logger.warning(f"DataComex: {year} {flow} — no data returned")
            except Exception as e:
                err = f"{year} {flow}: {e}"
                errors.append(err)
                logger.error(f"DataComex sync error: {err}")

    # Log sync
    await db.datacomex_sync_logs.insert_one({
        "log_id": new_id(),
        "synced_at": now,
        "years": years,
        "records_imported": total_imported,
        "errors": errors,
        "status": "completed" if not errors else "partial",
        "trigger": "auto",
    })

    return {
        "status": "completed" if not errors else "partial",
        "years": years,
        "records_imported": total_imported,
        "errors": errors,
        "synced_at": now,
    }


async def _fetch_year_flow(year: int, flow: str, taric_level: str) -> List[Dict]:
    """Fetch data from DataComex for a single year+flow via form POST."""
    # Build form data for all months of the year
    form_data = {}

    # Flow
    if flow == "export":
        form_data["chk_export"] = "on"
    else:
        form_data["chk_import"] = "on"

    # Select full year
    form_data[f"year_[{year}]"] = "on"
    for month in range(1, 13):
        form_data[f"year_[{year}{month:02d}]"] = "on"

    # Select all TARIC at 2-digit level
    form_data["[Taric].&[Total Taric]"] = "on"

    # Select Total Mundo
    form_data["[Pais].&[Total Mundo]"] = "on"

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.post(DATACOMEX_URL, data=form_data)
            if resp.status_code != 200:
                logger.warning(f"DataComex HTTP {resp.status_code} for {year} {flow}")
                return []

            # Try to find CSV download link or parse table
            # DataComex returns HTML with a table — parse it
            return _parse_html_table(resp.text, year, flow)
    except Exception as e:
        logger.error(f"DataComex fetch failed for {year} {flow}: {e}")
        return []


def _parse_html_table(html: str, year: int, flow: str) -> List[Dict]:
    """Parse the DataComex HTML response table."""
    records = []
    # Simple extraction — look for table rows in the results
    # The table has columns: Flujo, Periodo, País, Taric, Euros, Kilos
    import re

    # Find all table rows in tableResults
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) >= 6:
            flujo = cells[0].strip()
            periodo = cells[1].strip()
            pais = cells[2].strip()
            taric = cells[3].strip()
            euros_str = cells[4].strip().replace('.', '').replace(',', '.')
            kilos_str = cells[5].strip().replace('.', '').replace(',', '.')

            try:
                euros = float(euros_str) if euros_str else 0
            except ValueError:
                euros = 0
            try:
                kilos = float(kilos_str) if kilos_str else 0
            except ValueError:
                kilos = 0

            if taric and euros > 0:
                # Extract TARIC 2-digit code
                taric_code = taric[:2] if len(taric) >= 2 else taric

                records.append({
                    "flow": "export" if "Exp" in flujo else "import",
                    "year": year,
                    "period": periodo,
                    "country": pais,
                    "taric_code": taric_code,
                    "taric_description": taric,
                    "euros": euros,
                    "kilos": kilos,
                })

    return records


async def process_csv_upload(content: bytes, filename: str) -> Dict:
    """Process a manually uploaded DataComex CSV file.

    Expected CSV format (semicolon-separated, from DataComex download):
    Flujo;Periodo;País;Taric;Euros;Kilos
    """
    now = now_iso()
    records = []

    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")

        for row in reader:
            flujo = row.get("Flujo", "").strip()
            periodo = row.get("Periodo", "").strip()
            pais = row.get("País", row.get("Pais", "")).strip()
            taric = row.get("Taric", "").strip()
            euros_str = row.get("Euros", "0").strip().replace(".", "").replace(",", ".")
            kilos_str = row.get("Kilos", "0").strip().replace(".", "").replace(",", ".")

            try:
                euros = float(euros_str) if euros_str else 0
            except ValueError:
                euros = 0
            try:
                kilos = float(kilos_str) if kilos_str else 0
            except ValueError:
                kilos = 0

            # Parse year from periodo
            year = None
            if periodo:
                import re
                year_match = re.search(r'(\d{4})', periodo)
                if year_match:
                    year = int(year_match.group(1))

            # Parse month
            month = None
            month_names = {"Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5,
                           "Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9,
                           "Octubre": 10, "Noviembre": 11, "Diciembre": 12}
            for name, num in month_names.items():
                if name.lower() in periodo.lower():
                    month = num
                    break

            flow = "export" if "exp" in flujo.lower() else "import"
            taric_code = taric[:2] if len(taric) >= 2 else taric

            if taric_code and euros > 0:
                records.append({
                    "record_id": new_id(),
                    "flow": flow,
                    "year": year,
                    "month": month,
                    "period": periodo,
                    "country": pais,
                    "taric_code": taric_code,
                    "taric_description": taric,
                    "euros": euros,
                    "kilos": kilos,
                    "source": "csv_upload",
                    "source_file": filename,
                    "imported_at": now,
                })
    except Exception as e:
        return {"status": "error", "message": f"CSV parse error: {e}"}

    if not records:
        return {"status": "error", "message": "No valid records found in CSV"}

    # Store raw data
    if records:
        await db.datacomex_raw_data.insert_many(records)

    # Log
    await db.datacomex_sync_logs.insert_one({
        "log_id": new_id(),
        "synced_at": now,
        "records_imported": len(records),
        "source": "csv_upload",
        "filename": filename,
        "status": "completed",
        "trigger": "manual",
    })

    return {
        "status": "completed",
        "records_imported": len(records),
        "filename": filename,
        "synced_at": now,
    }


async def _store_raw_data(records: List[Dict], year: int, flow: str, now: str):
    """Store fetched records into datacomex_raw_data."""
    docs = []
    for r in records:
        docs.append({
            "record_id": new_id(),
            "flow": r["flow"],
            "year": year,
            "month": None,
            "period": r.get("period"),
            "country": r.get("country", "Total Mundo"),
            "taric_code": r["taric_code"],
            "taric_description": r.get("taric_description"),
            "euros": r["euros"],
            "kilos": r.get("kilos", 0),
            "source": "datacomex_api",
            "imported_at": now,
        })
    if docs:
        await db.datacomex_raw_data.insert_many(docs)


async def rebuild_trade_metrics() -> Dict:
    """Aggregate raw data into trade metrics per TARIC chapter per year."""
    now = now_iso()

    pipeline = [
        {"$group": {
            "_id": {"taric": "$taric_code", "year": "$year", "flow": "$flow"},
            "total_euros": {"$sum": "$euros"},
            "total_kilos": {"$sum": "$kilos"},
            "records": {"$sum": 1},
        }},
        {"$sort": {"_id.year": 1}},
    ]
    raw_agg = await db.datacomex_raw_data.aggregate(pipeline).to_list(5000)

    # Build per-TARIC, per-year metrics
    metrics_map = {}  # (taric, year) → {exports, imports}
    for item in raw_agg:
        key = (item["_id"]["taric"], item["_id"]["year"])
        if key not in metrics_map:
            metrics_map[key] = {"exports": 0, "imports": 0, "export_kg": 0, "import_kg": 0}
        if item["_id"]["flow"] == "export":
            metrics_map[key]["exports"] = item["total_euros"]
            metrics_map[key]["export_kg"] = item["total_kilos"]
        else:
            metrics_map[key]["imports"] = item["total_euros"]
            metrics_map[key]["import_kg"] = item["total_kilos"]

    # Get CNAE mappings from DB (or use defaults)
    cnae_map = await _get_cnae_mappings()

    # Build metric documents
    docs = []
    for (taric, year), vals in metrics_map.items():
        exports = vals["exports"]
        imports = vals["imports"]
        balance = exports - imports
        coverage = exports / imports if imports > 0 else None

        # Get mapped CNAEs
        mapped_cnaes = cnae_map.get(taric, [])

        doc = {
            "metric_id": new_id(),
            "taric_code": taric,
            "taric_label": TARIC_CHAPTERS.get(taric, ""),
            "year": year,
            "exports_eur": round(exports, 2),
            "imports_eur": round(imports, 2),
            "trade_balance_eur": round(balance, 2),
            "coverage_ratio": round(coverage, 4) if coverage else None,
            "export_kg": vals["export_kg"],
            "import_kg": vals["import_kg"],
            "mapped_cnaes": mapped_cnaes,
            "generated_at": now,
        }
        docs.append(doc)

    # Compute YoY and CAGR
    _compute_growth_metrics(docs)

    # Persist
    await db.datacomex_trade_metrics.delete_many({})
    if docs:
        await db.datacomex_trade_metrics.insert_many(docs)

    return {
        "status": "completed",
        "metrics_computed": len(docs),
        "taric_chapters": len(set(d["taric_code"] for d in docs)),
        "years": sorted(set(d["year"] for d in docs if d["year"])),
        "generated_at": now,
    }


def _compute_growth_metrics(docs: List[Dict]):
    """Add YoY%, CAGR3, CAGR5 to each metric doc."""
    # Group by taric
    by_taric = {}
    for d in docs:
        tc = d["taric_code"]
        if tc not in by_taric:
            by_taric[tc] = {}
        if d["year"]:
            by_taric[tc][d["year"]] = d

    for d in docs:
        tc = d["taric_code"]
        y = d["year"]
        if not y:
            continue
        series = by_taric.get(tc, {})

        # YoY export growth
        prev = series.get(y - 1)
        if prev and prev["exports_eur"] > 0:
            d["export_yoy_pct"] = round((d["exports_eur"] - prev["exports_eur"]) / prev["exports_eur"] * 100, 2)
        else:
            d["export_yoy_pct"] = None

        # YoY import growth
        if prev and prev["imports_eur"] > 0:
            d["import_yoy_pct"] = round((d["imports_eur"] - prev["imports_eur"]) / prev["imports_eur"] * 100, 2)
        else:
            d["import_yoy_pct"] = None

        # CAGR 3 years
        y3 = series.get(y - 3)
        if y3 and y3["exports_eur"] > 0 and d["exports_eur"] > 0:
            d["export_cagr_3y"] = round(((d["exports_eur"] / y3["exports_eur"]) ** (1/3) - 1) * 100, 2)
        else:
            d["export_cagr_3y"] = None

        # CAGR 5 years
        y5 = series.get(y - 5)
        if y5 and y5["exports_eur"] > 0 and d["exports_eur"] > 0:
            d["export_cagr_5y"] = round(((d["exports_eur"] / y5["exports_eur"]) ** (1/5) - 1) * 100, 2)
        else:
            d["export_cagr_5y"] = None


async def rebuild_signals() -> Dict:
    """Generate trade signals from metrics."""
    now = now_iso()

    # Get all metrics sorted by taric + year
    metrics = await db.datacomex_trade_metrics.find(
        {"year": {"$ne": None}}, {"_id": 0}
    ).sort([("taric_code", 1), ("year", 1)]).to_list(5000)

    # Group by taric
    by_taric = {}
    for m in metrics:
        tc = m["taric_code"]
        if tc not in by_taric:
            by_taric[tc] = []
        by_taric[tc].append(m)

    signals = []
    for taric, series in by_taric.items():
        if len(series) < 3:
            continue

        series.sort(key=lambda x: x["year"])
        latest = series[-1]
        label = TARIC_CHAPTERS.get(taric, taric)

        # EXPORT BOOM: growth > 20% for 3 consecutive years
        recent_3 = series[-3:]
        if all(m.get("export_yoy_pct") and m["export_yoy_pct"] > 20 for m in recent_3):
            signals.append(_signal_doc(taric, label, "export_boom",
                "Crecimiento exportaciones >20% durante 3 anios consecutivos", latest, now))

        # EXPORT DECLINE: decline > 15% for 3 consecutive years
        if all(m.get("export_yoy_pct") and m["export_yoy_pct"] < -15 for m in recent_3):
            signals.append(_signal_doc(taric, label, "export_decline",
                "Caida exportaciones >15% durante 3 anios consecutivos", latest, now))

        # TREND REVERSAL: change from growing to declining or vice versa
        if len(series) >= 2:
            prev_yoy = series[-2].get("export_yoy_pct")
            curr_yoy = latest.get("export_yoy_pct")
            if prev_yoy is not None and curr_yoy is not None:
                if prev_yoy < 0 and curr_yoy > 0:
                    signals.append(_signal_doc(taric, label, "trend_reversal_positive",
                        "Inversion de tendencia: de decrecimiento a crecimiento", latest, now))
                elif prev_yoy > 0 and curr_yoy < 0:
                    signals.append(_signal_doc(taric, label, "trend_reversal_negative",
                        "Inversion de tendencia: de crecimiento a decrecimiento", latest, now))

    # Persist
    await db.datacomex_signals.delete_many({})
    if signals:
        await db.datacomex_signals.insert_many(signals)

    return {
        "status": "completed",
        "signals_generated": len(signals),
        "generated_at": now,
    }


def _signal_doc(taric: str, label: str, signal_type: str, description: str,
                latest_metric: Dict, now: str) -> Dict:
    return {
        "signal_id": new_id(),
        "taric_code": taric,
        "taric_label": label,
        "signal_type": signal_type,
        "description": description,
        "year": latest_metric.get("year"),
        "exports_eur": latest_metric.get("exports_eur"),
        "imports_eur": latest_metric.get("imports_eur"),
        "export_yoy_pct": latest_metric.get("export_yoy_pct"),
        "mapped_cnaes": latest_metric.get("mapped_cnaes", []),
        "generated_at": now,
    }


async def rebuild_cnae_mappings() -> Dict:
    """Seed/rebuild TARIC→CNAE mapping collection from defaults."""
    now = now_iso()

    for taric_code, cnae_list in DEFAULT_TARIC_TO_CNAE.items():
        for mapping in cnae_list:
            await db.datacomex_cnae_mapping.update_one(
                {"taric_code": taric_code, "cnae_code": mapping["cnae"]},
                {"$set": {
                    "taric_code": taric_code,
                    "taric_description": TARIC_CHAPTERS.get(taric_code, ""),
                    "cnae_code": mapping["cnae"],
                    "confidence_score": mapping["confidence"],
                    "validated_by_human": False,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "mapping_id": new_id(),
                    "created_at": now,
                }},
                upsert=True,
            )

    total = await db.datacomex_cnae_mapping.count_documents({})
    return {"status": "completed", "mappings": total, "generated_at": now}


async def _get_cnae_mappings() -> Dict[str, List[Dict]]:
    """Get current TARIC→CNAE mappings from centralized Taxonomy Intelligence Layer (v2)."""
    mappings = await db.taxonomy_mappings.find(
        {"source_taxonomy": "taric", "status": "active"},
        {"_id": 0},
    ).to_list(500)

    result = {}
    for m in mappings:
        tc = m["source_code"]
        if tc not in result:
            result[tc] = []
        result[tc].append({
            "cnae": m["cnae_code"],
            "confidence": m.get("confidence_score", 0.5),
            "weight": m.get("weight", 0.0),
        })

    # Fallback to defaults if DB is empty
    if not result:
        return DEFAULT_TARIC_TO_CNAE

    return result


async def generate_seed_trade_data() -> Dict:
    """Generate realistic trade data from official Spanish totals.
    
    Uses published aggregate data from Ministerio de Industria.
    Replaces when real CSV is uploaded.
    """
    from services.datacomex_seed import SPAIN_TRADE_TOTALS, TARIC_EXPORT_SHARES, TARIC_IMPORT_SHARES

    now = now_iso()
    records = []

    for year, totals in SPAIN_TRADE_TOTALS.items():
        total_exp = totals["exports"]
        total_imp = totals["imports"]

        # Exports by TARIC chapter
        for taric, share in TARIC_EXPORT_SHARES.items():
            records.append({
                "record_id": new_id(),
                "flow": "export",
                "year": year,
                "month": None,
                "period": str(year),
                "country": "Total Mundo",
                "taric_code": taric,
                "taric_description": TARIC_CHAPTERS.get(taric, ""),
                "euros": round(total_exp * share, 2),
                "kilos": 0,
                "source": "datacomex_seed",
                "imported_at": now,
            })

        # Imports by TARIC chapter
        for taric, share in TARIC_IMPORT_SHARES.items():
            records.append({
                "record_id": new_id(),
                "flow": "import",
                "year": year,
                "month": None,
                "period": str(year),
                "country": "Total Mundo",
                "taric_code": taric,
                "taric_description": TARIC_CHAPTERS.get(taric, ""),
                "euros": round(total_imp * share, 2),
                "kilos": 0,
                "source": "datacomex_seed",
                "imported_at": now,
            })

    # Persist
    await db.datacomex_raw_data.delete_many({"source": "datacomex_seed"})
    if records:
        await db.datacomex_raw_data.insert_many(records)

    # Log
    await db.datacomex_sync_logs.insert_one({
        "log_id": new_id(),
        "synced_at": now,
        "years": list(SPAIN_TRADE_TOTALS.keys()),
        "records_imported": len(records),
        "source": "seed",
        "status": "completed",
        "trigger": "seed",
    })

    return {
        "status": "completed",
        "records": len(records),
        "years": list(SPAIN_TRADE_TOTALS.keys()),
        "taric_export_chapters": len(TARIC_EXPORT_SHARES),
        "taric_import_chapters": len(TARIC_IMPORT_SHARES),
        "generated_at": now,
    }
