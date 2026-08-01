"""ARROBA Copilot — feedback + sesgo de ranking (copilot-feedback-v1).

Aprende del comportamiento del usuario (aceptó/descartó/ignoró/resultado) y ajusta un **sesgo de
preferencia** que SOLO reordena el surfacing/ranking (qué se muestra antes), POR USUARIO. Reglas duras
(decisiones de Daniel 2026-07-31):
  - Ventana de 90 días (lo más antiguo deja de contar).
  - Tope **±10 %** por dimensión (sector, tamaño).
  - Explicable y reversible: cada sesgo lleva su razón ("−10 % en sector retail: 3 descartes en 90 días").
  - NUNCA toca el score/banda del comité (eso es determinista); solo el orden de presentación.
Best-effort sobre BBDD. Ver memory/ARROBA_COPILOT_MEMORY_SESSIONS_PERSONALIZATION.md (§1.4, §8).
"""

import time
from typing import Dict, List, Optional

FEEDBACK_VERSION = "copilot-feedback-v1"
WINDOW_DAYS = 90
CAP = 0.10                                   # tope ±10 %
_WINDOW_SECS = WINDOW_DAYS * 86400

# Peso de cada evento sobre el sesgo (se suma y luego se recorta a ±CAP).
EVENT_WEIGHT = {"accept": 0.03, "dismiss": -0.03, "ignore": -0.01,
                "outcome_success": 0.05, "outcome_failure": -0.05}
_EVENTS = set(EVENT_WEIGHT)
_DIMS = ("sector", "size")


def _now() -> str:
    try:
        from models import now_iso
        return now_iso()
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def size_bucket(revenue) -> Optional[str]:
    try:
        r = float(revenue)
    except Exception:
        return None
    if r < 1e7:
        return "small"
    if r < 5e7:
        return "mid"
    return "large"


def dims_from_inputs(inputs: Dict) -> Dict:
    inputs = inputs or {}
    return {"sector": (inputs.get("identity") or {}).get("cnae_section"),
            "size": size_bucket((inputs.get("kpis") or {}).get("revenue"))}


async def record(tenant_id, user_id, event: str, company_id=None,
                 dimensions: Optional[Dict] = None, notes: Optional[str] = None) -> Dict:
    if event not in _EVENTS:
        return {"recorded": False, "reason": "unknown_event", "valid_events": sorted(_EVENTS)}
    dims = {k: (dimensions or {}).get(k) for k in _DIMS if (dimensions or {}).get(k) is not None}
    ev = {"tenant_id": tenant_id, "user_id": user_id, "event": event, "company_id": company_id,
          "dimensions": dims, "notes": notes, "recorded_at": _now(), "ts": time.time()}
    if tenant_id and user_id:
        try:
            from database import db
            await db.copilot_feedback.insert_one(dict(ev))
        except Exception:
            pass
        try:
            from services.copilot import governance as GOV
            await GOV.audit("feedback", tenant_id, user_id, {"event": event})
        except Exception:
            pass
    return {"recorded": True, "event": event, "company_id": company_id, "dimensions": dims}


async def _recent_events(tenant_id, user_id) -> List[Dict]:
    if not (tenant_id and user_id):
        return []
    cutoff = time.time() - _WINDOW_SECS
    try:
        from database import db
        out = []
        async for d in db.copilot_feedback.find(
                {"tenant_id": tenant_id, "user_id": user_id}, {"_id": 0}).limit(2000):
            if float(d.get("ts") or 0) >= cutoff:
                out.append(d)
        return out
    except Exception:
        return []


def _reason(key: str, bias: float, pos: int, neg: int) -> str:
    dim, val = key.split(":", 1)
    pct = abs(round(bias * 100))
    sign = "+" if bias >= 0 else "−"
    dimname = {"sector": "sector", "size": "tamaño"}.get(dim, dim)
    if bias >= 0:
        return f"{sign}{pct}% en {dimname} {val}: {pos} aceptaciones en {WINDOW_DAYS} días"
    return f"{sign}{pct}% en {dimname} {val}: {neg} descartes en {WINDOW_DAYS} días"


async def compute_bias(tenant_id, user_id) -> Dict:
    """Sesgo por 'dim:valor' (sector/tamaño) a partir del feedback reciente. Acotado y explicable."""
    events = await _recent_events(tenant_id, user_id)
    agg: Dict[str, Dict] = {}
    for e in events:
        w = EVENT_WEIGHT.get(e.get("event"), 0.0)
        if not w:
            continue
        dims = e.get("dimensions") or {}
        for dim in _DIMS:
            v = dims.get(dim)
            if v is None:
                continue
            a = agg.setdefault(f"{dim}:{v}", {"raw": 0.0, "n": 0, "pos": 0, "neg": 0})
            a["raw"] += w
            a["n"] += 1
            a["pos" if w > 0 else "neg"] += 1
    out: Dict[str, Dict] = {}
    for key, a in agg.items():
        b = round(max(-CAP, min(CAP, a["raw"])), 4)
        if b == 0:
            continue
        out[key] = {"bias": b, "events": a["n"], "reason": _reason(key, b, a["pos"], a["neg"])}
    return out


def summarize(bias: Dict) -> List[str]:
    return [v["reason"] for v in (bias or {}).values()]


def _match(dims: Dict, bias: Dict):
    total, reasons = 0.0, []
    for dim in _DIMS:
        v = dims.get(dim)
        key = f"{dim}:{v}"
        if v is not None and key in bias:
            total += bias[key]["bias"]
            reasons.append(bias[key]["reason"])
    total = round(max(-CAP, min(CAP, total)), 4)
    return total, reasons


def rank_with_bias(items: List[Dict], key_field: str, base_field: str, base_max: float,
                   dims_by_key: Dict, bias: Dict) -> List[Dict]:
    """Reordena por surfacing_score = base·(1+sesgo). NO altera base_field (score del comité)."""
    if not bias or not items:
        return items
    out = []
    for it in items:
        base = (it.get(base_field) or 0) / (base_max or 1)
        bval, reasons = _match(dims_by_key.get(it.get(key_field), {}), bias)
        out.append({**it, "surfacing_score": round(base * (1 + bval), 6),
                    "bias_applied": {"value": bval, "reasons": reasons}})
    return sorted(out, key=lambda x: -x["surfacing_score"])
