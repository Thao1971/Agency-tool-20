"""Business Demography — INE DIRCE + Sociedades Mercantiles connector.

Sources:
- DIRCE (op 43, table 39375): Active companies (annual)
- Sociedades Mercantiles (op 125, table 13912): Created/dissolved monthly
"""

import logging
from typing import Dict, List
from database import db
from models import new_id, now_iso
from services.macro_intelligence import TREND_DIRECTION, TREND_STRENGTH

logger = logging.getLogger(__name__)

INE_BASE = "https://servicios.ine.es/wstempus/js/ES"

# Table IDs
TABLE_SOC_MERCANTILES = 13912  # Monthly: created + dissolved
TABLE_DIRCE_EMPRESAS = 39375   # Annual: active companies

# Series name patterns for national totals
SERIES_PATTERNS = {
    "companies_created": "Constituídas. Número de Sociedades. Total Nacional. Mercantiles",
    "companies_dissolved": "Disueltas. Número de Sociedades. Total Nacional. Mercantiles",
    "companies_active": "Nacional. Total. Total.",
}


async def sync_business_demography(nult: int = 24) -> Dict:
    """Sync business demography data from INE."""
    import httpx
    now = now_iso()
    stats = {"created_points": 0, "dissolved_points": 0, "active_points": 0, "errors": 0}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Sociedades Mercantiles (monthly)
            r = await client.get(f"{INE_BASE}/DATOS_TABLA/{TABLE_SOC_MERCANTILES}", params={"nult": nult})
            soc_data = r.json()

            for series in soc_data:
                name = series.get("Nombre", "")
                indicator_key = None

                if SERIES_PATTERNS["companies_created"] in name:
                    indicator_key = "companies_created"
                elif SERIES_PATTERNS["companies_dissolved"] in name:
                    indicator_key = "companies_dissolved"
                else:
                    continue

                for dp in series.get("Data", []):
                    if dp.get("Secreto") or dp.get("Valor") is None:
                        continue
                    date = f"{dp['Anyo']}-{dp['FK_Periodo']:02d}-01T00:00:00Z" if dp.get("FK_Periodo") else f"{dp['Anyo']}-01-01T00:00:00Z"

                    await db.business_demography.update_one(
                        {"indicator_key": indicator_key, "date": date},
                        {"$set": {
                            "indicator_key": indicator_key,
                            "indicator_name": "Sociedades constituidas" if indicator_key == "companies_created" else "Sociedades disueltas",
                            "value": dp["Valor"],
                            "year": dp["Anyo"],
                            "period": dp.get("FK_Periodo"),
                            "date": date,
                            "frequency": "monthly",
                            "unit": "unidades",
                            "source": "INE",
                            "source_table": TABLE_SOC_MERCANTILES,
                            "source_operation": "Sociedades Mercantiles",
                            "last_updated_at": now,
                            "status": "ok",
                        }},
                        upsert=True
                    )
                    stats[f"{indicator_key.split('_')[1]}_points"] += 1

            # 2. DIRCE (annual)
            r2 = await client.get(f"{INE_BASE}/DATOS_TABLA/{TABLE_DIRCE_EMPRESAS}", params={"nult": 5})
            dirce_data = r2.json()

            for series in dirce_data:
                name = series.get("Nombre", "")
                if name.strip() != SERIES_PATTERNS["companies_active"]:
                    continue

                for dp in series.get("Data", []):
                    if dp.get("Secreto") or dp.get("Valor") is None:
                        continue
                    date = f"{dp['Anyo']}-01-01T00:00:00Z"

                    await db.business_demography.update_one(
                        {"indicator_key": "companies_active", "date": date},
                        {"$set": {
                            "indicator_key": "companies_active",
                            "indicator_name": "Empresas activas",
                            "value": dp["Valor"],
                            "year": dp["Anyo"],
                            "period": None,
                            "date": date,
                            "frequency": "annual",
                            "unit": "unidades",
                            "source": "INE",
                            "source_table": TABLE_DIRCE_EMPRESAS,
                            "source_operation": "DIRCE",
                            "last_updated_at": now,
                            "status": "ok",
                        }},
                        upsert=True
                    )
                    stats["active_points"] += 1

        # Compute changes and net balance
        await _compute_demography_changes()

        await db.data_provider_status.update_one(
            {"provider": "ine_demography"},
            {"$set": {"status": "ok", "last_sync_at": now, "last_error": None,
                      "records_count": await db.business_demography.count_documents({}), "updated_at": now}},
            upsert=True
        )

        return {"status": "completed", **stats, "total": sum(stats.values()) - stats["errors"]}

    except Exception as e:
        logger.error(f"Business demography sync failed: {e}")
        await db.data_provider_status.update_one(
            {"provider": "ine_demography"},
            {"$set": {"status": "error", "last_error": str(e)[:200], "updated_at": now}},
            upsert=True
        )
        return {"status": "error", "error": str(e)[:200]}


async def _compute_demography_changes():
    """Compute YoY, MoM, net balance, trends, and semantic signals."""
    for key in ["companies_created", "companies_dissolved"]:
        history = await db.business_demography.find(
            {"indicator_key": key}, {"_id": 0}
        ).sort("date", -1).limit(25).to_list(25)

        if len(history) < 2:
            continue

        latest = history[0]
        prev_month = history[1] if len(history) > 1 else None
        prev_year = history[12] if len(history) > 12 else None

        update = {}
        if prev_month and prev_month["value"]:
            update["previous_value"] = prev_month["value"]
            update["mom_change_abs"] = round(latest["value"] - prev_month["value"])
            update["mom_change_pct"] = round((latest["value"] - prev_month["value"]) / prev_month["value"] * 100, 2)

        if prev_year and prev_year["value"]:
            update["yoy_value"] = prev_year["value"]
            update["yoy_change_abs"] = round(latest["value"] - prev_year["value"])
            update["yoy_change_pct"] = round((latest["value"] - prev_year["value"]) / prev_year["value"] * 100, 2)

        # Trend
        if update.get("yoy_change_pct") is not None:
            pct = update["yoy_change_pct"]
            update["trend_direction"] = "up" if pct > 2 else "down" if pct < -2 else "stable"
            update["trend_strength"] = "strong" if abs(pct) > 10 else "moderate" if abs(pct) > 3 else "weak"

        # Sparkline
        update["sparkline_12m"] = [h["value"] for h in reversed(history[:12]) if h.get("value")]
        update["sparkline_24m"] = [h["value"] for h in reversed(history[:24]) if h.get("value")]

        if update:
            await db.business_demography.update_one(
                {"indicator_key": key, "date": latest["date"]},
                {"$set": update}
            )

    # Net balance (created - dissolved) for same periods
    created_list = await db.business_demography.find(
        {"indicator_key": "companies_created"}, {"_id": 0}
    ).sort("date", -1).limit(24).to_list(24)

    dissolved_map = {}
    dissolved_list = await db.business_demography.find(
        {"indicator_key": "companies_dissolved"}, {"_id": 0}
    ).sort("date", -1).limit(24).to_list(24)
    for d in dissolved_list:
        dissolved_map[d["date"]] = d["value"]

    for c in created_list:
        diss = dissolved_map.get(c["date"])
        if diss is not None:
            net = c["value"] - diss
            await db.business_demography.update_one(
                {"indicator_key": "net_balance", "date": c["date"]},
                {"$set": {
                    "indicator_key": "net_balance",
                    "indicator_name": "Saldo neto empresarial",
                    "value": net,
                    "year": c["year"],
                    "period": c.get("period"),
                    "date": c["date"],
                    "frequency": "monthly",
                    "unit": "unidades",
                    "source": "INE",
                    "source_table": TABLE_SOC_MERCANTILES,
                    "created_value": c["value"],
                    "dissolved_value": diss,
                    "trend_direction": "up" if net > 0 else "down" if net < 0 else "stable",
                    "status": "ok",
                    "last_updated_at": now_iso(),
                }},
                upsert=True
            )

    # Semantic signals
    latest_created = created_list[0] if created_list else None
    if latest_created:
        yoy = latest_created.get("yoy_change_pct", 0)
        if yoy > 5:
            signal = "business_expansion"
            impact = "positive"
        elif yoy < -5:
            signal = "business_contraction"
            impact = "negative"
        elif yoy > 0:
            signal = "moderate_growth"
            impact = "slightly_positive"
        else:
            signal = "stable_activity"
            impact = "neutral"

        await db.business_demography.update_one(
            {"indicator_key": "companies_created", "date": latest_created["date"]},
            {"$set": {"semantic_signal": signal, "semantic_impact": impact}}
        )
