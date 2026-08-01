"""ARROBA Copilot — observabilidad (copilot-metrics-v1).

Registra una métrica compacta POR TURNO (nivel, latencia, degradado, cobertura, si hubo NBA/card) para
poder iterar con datos: ¿acierta el enrutado? ¿dónde se abstiene? ¿latencia? Best-effort: si no hay
BBDD, no rompe (además emite un log estructurado). No guarda contenido de la conversación, solo señales.
"""

import logging
import time
from typing import Dict, List, Optional

METRICS_VERSION = "copilot-metrics-v1"
logger = logging.getLogger("copilot.metrics")


def _now() -> str:
    try:
        from models import now_iso
        return now_iso()
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


async def record_turn(doc: Dict) -> None:
    """Persiste + loguea una métrica de turno. Nunca lanza."""
    row = {"metrics_version": METRICS_VERSION, "at": _now(), "ts": time.time(), **doc}
    try:
        logger.info("copilot_turn %s", {k: row.get(k) for k in
                    ("level", "kind", "capability", "degraded", "response_ms", "coverage",
                     "n_actions", "had_card")})
    except Exception:
        pass
    try:
        from database import db
        await db.copilot_metrics.insert_one(dict(row))
    except Exception:
        pass


def _pct(x: float) -> float:
    return round(x, 4)


async def summary(tenant_id: Optional[str] = None, user_id: Optional[str] = None,
                  limit: int = 5000) -> Dict:
    """Agrega las métricas recientes: volumen, distribución de niveles, tasa de degradado, latencia
    (media y p95), cobertura media y tasa de NBA. Nunca lanza."""
    q: Dict = {}
    if tenant_id:
        q["tenant_id"] = tenant_id
    if user_id:
        q["user_id"] = user_id
    rows: List[Dict] = []
    try:
        from database import db
        async for d in db.copilot_metrics.find(q, {"_id": 0}).sort("ts", -1).limit(limit):
            rows.append(d)
    except Exception:
        pass
    n = len(rows)
    if not n:
        return {"metrics_version": METRICS_VERSION, "turns": 0}

    by_level: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    lat = [r["response_ms"] for r in rows if isinstance(r.get("response_ms"), (int, float))]
    cov = [r["coverage"] for r in rows if isinstance(r.get("coverage"), (int, float))]
    degraded = sum(1 for r in rows if r.get("degraded"))
    with_nba = sum(1 for r in rows if (r.get("n_actions") or 0) > 0)
    for r in rows:
        by_level[r.get("level")] = by_level.get(r.get("level"), 0) + 1
        if r.get("kind"):
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1

    lat_sorted = sorted(lat)
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))] if lat_sorted else None

    return {
        "metrics_version": METRICS_VERSION,
        "turns": n,
        "by_level": by_level,
        "by_kind": by_kind,
        "degraded_rate": _pct(degraded / n),
        "nba_rate": _pct(with_nba / n),
        "latency_ms": {"avg": round(sum(lat) / len(lat), 1) if lat else None, "p95": p95},
        "coverage_avg": round(sum(cov) / len(cov), 4) if cov else None,
    }
