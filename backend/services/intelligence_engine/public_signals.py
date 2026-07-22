"""Signal Engine extension — señales derivadas de las 3 fuentes públicas nuevas.

Cero datos sintéticos: cada señal se computa a partir de filas reales y se
persiste en `economic_signals` con `signal_source` para trazabilidad.
"""

from datetime import datetime, timezone
from database import db
from models import new_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _upsert_signal(signal: dict) -> None:
    signal.setdefault("signal_id", new_id())
    signal.setdefault("created_at", _now())
    await db.economic_signals.update_one(
        {"signal_type": signal["signal_type"], "scope": signal.get("scope")},
        {"$set": signal}, upsert=True,
    )


# ── Ayudas y subvenciones ────────────────────────────────────────────────────
async def signals_from_ayudas() -> int:
    n = 0
    # Agregamos por CIF
    pipeline = [
        {"$match": {"cif_normalized": {"$ne": ""}}},
        {"$group": {"_id": "$cif_normalized",
                    "total": {"$sum": "$amount_eur"},
                    "count": {"$sum": 1},
                    "programs": {"$addToSet": "$program"}}},
        {"$match": {"$or": [{"count": {"$gte": 3}}, {"total": {"$gte": 500000}}]}},
    ]
    async for row in db.ayudas_subvenciones_publicas.aggregate(pipeline):
        cif = row["_id"]
        if row["count"] >= 3:
            await _upsert_signal({
                "signal_type": "recurring_grant_recipient",
                "scope": cif, "label": "Receptor recurrente de ayudas públicas",
                "evidence": {"count": row["count"], "total_eur": row["total"]},
                "signal_source": "ayudas_subvenciones_publicas",
            }); n += 1
        if row["total"] >= 500000:
            await _upsert_signal({
                "signal_type": "high_public_funding",
                "scope": cif, "label": "Elevada financiación pública",
                "evidence": {"total_eur": row["total"]},
                "signal_source": "ayudas_subvenciones_publicas",
            }); n += 1
        if any("europ" in (p or "").lower() or "fse" in (p or "").lower() or "feder" in (p or "").lower()
               for p in row["programs"]):
            await _upsert_signal({
                "signal_type": "eu_funds_beneficiary",
                "scope": cif, "label": "Beneficiario de fondos europeos",
                "evidence": {"programs": list(row["programs"])},
                "signal_source": "ayudas_subvenciones_publicas",
            }); n += 1
    return n


# ── Empleo ───────────────────────────────────────────────────────────────────
async def signals_from_empleo() -> int:
    n = 0
    async for row in db.estadisticas_empleo.find({}, {"_id": 0}).sort("period", -1).limit(500):
        ccaa = row.get("ccaa")
        rate = row.get("unemployment_rate")
        if not ccaa or rate is None:
            continue
        if rate < 10:  # umbral favorable (paro < 10%)
            await _upsert_signal({
                "signal_type": "favorable_labor_market",
                "scope": ccaa, "label": "Mercado laboral favorable",
                "evidence": {"unemployment_rate": rate, "period": row.get("period")},
                "signal_source": "estadisticas_empleo",
            }); n += 1
    return n


# ── Territoriales ────────────────────────────────────────────────────────────
async def signals_from_territoriales() -> int:
    n = 0
    # Renta media nacional aproximada (referencia)
    avg_pipeline = [{"$group": {"_id": None, "avg": {"$avg": "$average_income"}}}]
    cursor = db.estadisticas_territoriales.aggregate(avg_pipeline)
    national_avg = 0
    async for r in cursor:
        national_avg = r["avg"]
    async for row in db.estadisticas_territoriales.find({}, {"_id": 0}).sort("year", -1).limit(1000):
        prov = row.get("province")
        income = row.get("average_income")
        if not prov or income is None:
            continue
        if national_avg and income >= national_avg * 1.15:
            await _upsert_signal({
                "signal_type": "high_disposable_income",
                "scope": prov, "label": "Alta renta disponible",
                "evidence": {"average_income": income, "national_avg": national_avg, "year": row.get("year")},
                "signal_source": "estadisticas_territoriales",
            }); n += 1
    return n


async def rebuild_public_signals() -> dict:
    """Recompute all public-source signals. Idempotent (upsert by signal_type+scope)."""
    return {
        "ayudas": await signals_from_ayudas(),
        "empleo": await signals_from_empleo(),
        "territoriales": await signals_from_territoriales(),
    }
