"""Business Demography — Public endpoints for Arroba/Valuo consumption."""

from fastapi import APIRouter, Depends, Query
from database import db
from models import now_iso
from auth_utils import get_current_user
from services.business_demography import sync_business_demography
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/public/business-demography", tags=["business_demography"])

CONTRACT_VERSION = "1.0"


def _meta(t0):
    return {"contract_version": CONTRACT_VERSION, "generated_at": now_iso(),
            "response_time_ms": round((time.time() - t0) * 1000, 1),
            "source": "INE — DIRCE + Sociedades Mercantiles",
            "source_attribution": "Instituto Nacional de Estadistica. Datos oficiales publicos."}


async def _latest(key):
    return await db.business_demography.find_one(
        {"indicator_key": key, "status": "ok"}, {"_id": 0}, sort=[("date", -1)]
    )


MONTH_NAMES_ES = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
MONTH_NAMES_SHORT = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}


def _card(ind, label):
    if not ind:
        return {"value": None, "change_pct": None, "trend": None}
    # change_pct as decimal for Arroba (0.008 = 0.8%)
    yoy = ind.get("yoy_change_pct")
    change_decimal = round(yoy / 100, 4) if yoy is not None else None
    return {
        "value": int(ind["value"]) if ind.get("value") is not None else None,
        "change_pct": change_decimal,
        "trend": ind.get("trend_direction"),
    }


def _period_label(ind):
    if not ind:
        return None
    p = ind.get("period")
    y = ind.get("year")
    if p and y:
        return f"{MONTH_NAMES_ES.get(p, str(p))}. {y}"
    elif y:
        return str(y)
    return None


@router.get("/overview")
async def overview():
    """Homepage-ready overview for Arroba. Stable contract."""
    t0 = time.time()
    active = await _latest("companies_active")
    created = await _latest("companies_created")
    dissolved = await _latest("companies_dissolved")
    net = await _latest("net_balance")

    return {
        **_meta(t0),
        "active_companies": _card(active, "Empresas activas"),
        "new_companies": _card(created, "Sociedades constituidas"),
        "closed_companies": _card(dissolved, "Sociedades disueltas"),
        "net_balance": {"value": int(net["value"]) if net and net.get("value") is not None else None},
        "period": _period_label(created) or _period_label(dissolved),
    }


@router.get("/active-companies")
async def active_companies():
    t0 = time.time()
    latest = await _latest("companies_active")
    history = await db.business_demography.find(
        {"indicator_key": "companies_active"}, {"_id": 0}
    ).sort("date", -1).to_list(20)
    return {**_meta(t0), "current": _card(latest, "Empresas activas"), "history": history}


@router.get("/new-companies")
async def new_companies():
    t0 = time.time()
    latest = await _latest("companies_created")
    history = await db.business_demography.find(
        {"indicator_key": "companies_created"}, {"_id": 0}
    ).sort("date", -1).to_list(36)
    return {**_meta(t0), "current": _card(latest, "Sociedades constituidas"), "history": history}


@router.get("/closed-companies")
async def closed_companies():
    t0 = time.time()
    latest = await _latest("companies_dissolved")
    history = await db.business_demography.find(
        {"indicator_key": "companies_dissolved"}, {"_id": 0}
    ).sort("date", -1).to_list(36)
    return {**_meta(t0), "current": _card(latest, "Sociedades disueltas"), "history": history}


@router.get("/history")
async def full_history(limit: int = Query(12, ge=1, le=60)):
    """Historical series as arrays for Arroba charts."""
    t0 = time.time()

    created_hist = await db.business_demography.find(
        {"indicator_key": "companies_created", "value": {"$ne": None}}, {"_id": 0}
    ).sort("date", -1).limit(limit).to_list(limit)

    dissolved_hist = await db.business_demography.find(
        {"indicator_key": "companies_dissolved", "value": {"$ne": None}}, {"_id": 0}
    ).sort("date", -1).limit(limit).to_list(limit)

    active_hist = await db.business_demography.find(
        {"indicator_key": "companies_active", "value": {"$ne": None}}, {"_id": 0}
    ).sort("date", -1).limit(limit).to_list(limit)

    # Reverse to chronological order
    created_hist.reverse()
    dissolved_hist.reverse()
    active_hist.reverse()

    # Build dissolved lookup by (year, period)
    dissolved_map = {}
    for d in dissolved_hist:
        key = (d.get("year"), d.get("period"))
        dissolved_map[key] = d

    # Build aligned arrays
    months = []
    created_vals = []
    closed_vals = []

    for c in created_hist:
        p = c.get("period")
        y = c.get("year")
        if p and y:
            month_label = f"{MONTH_NAMES_ES.get(p, str(p))}. {y}"
            months.append(month_label)
            created_vals.append(int(c["value"]))
            diss = dissolved_map.get((y, p))
            closed_vals.append(int(diss["value"]) if diss and diss.get("value") else 0)

    # Active: annual data — interpolate to monthly if needed, or return as-is
    active_vals = []
    if active_hist:
        # For each month in created, find the closest active year
        for c in created_hist:
            y = c.get("year")
            best = None
            for a in active_hist:
                if a["year"] <= y:
                    if best is None or a["year"] > best["year"]:
                        best = a
            active_vals.append(int(best["value"]) if best else None)

    return {
        **_meta(t0),
        "months": months,
        "created": created_vals,
        "closed": closed_vals,
        "active": active_vals,
    }


# Admin: sync
@router.post("/sync")
async def sync(user=Depends(get_current_user)):
    return await sync_business_demography(nult=36)
