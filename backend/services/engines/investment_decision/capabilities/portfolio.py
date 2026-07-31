"""Análisis de cartera (POST /portfolio). Agrega varias decisiones: score de cartera,
distribución por banda de recomendación, señal de concentración y miembros. Determinista.
(Diversificación por sector/tamaño y sinergias por Knowledge Graph: ampliable en v1.1.)"""

from typing import Dict, List
from services.engines.investment_decision import engine as IDE
from services.engines.investment_decision import evidence as EV


def _key(item: Dict) -> str:
    return item.get("opportunity_id") or item.get("company_id") or item.get("cif") or "op"


async def portfolio(opportunities: List[Dict], buyer_profile: Dict) -> Dict:
    members, bands, sectors = [], {}, {}
    scores = []
    for it in opportunities or []:
        req = {"opportunity_id": _key(it), "company_id": it.get("company_id"),
               "cif": it.get("cif"), "buyer_profile": buyer_profile, "inputs": it.get("inputs") or {}}
        r = await IDE.analyze(req)
        members.append({"opportunity_id": _key(it), "investment_score": r["investment_score"],
                        "recommendation": r["recommendation"], "confidence": r["confidence"]})
        scores.append(r["investment_score"])
        bands[r["recommendation"]] = bands.get(r["recommendation"], 0) + 1
        # diversificación por sector (best-effort, lectura ligera)
        try:
            ev = await EV.resolve_evidence(req)
            sec = (ev["bundle"].get("identity") or {}).get("cnae_section") or "n/d"
        except Exception:
            sec = "n/d"
        sectors[sec] = sectors.get(sec, 0) + 1

    n = len(members) or 1
    agg = int(round(sum(scores) / n)) if scores else 0
    conf = round(sum(m["confidence"] for m in members) / n, 4) if members else 0.0
    top_sector = max(sectors.values()) if sectors else 0
    flags = []
    if top_sector / n >= 0.6:
        flags.append("Concentración sectorial alta (≥60% de la cartera en un mismo sector).")
    return {"buyer_profile": (buyer_profile or {}).get("type"),
            "aggregate_score": agg, "confidence": conf,
            "diversification": {"by_band": bands, "by_sector": sectors},
            "concentration_flags": flags,
            "cross_synergies": [],   # Knowledge Graph — ampliable en v1.1
            "members": sorted(members, key=lambda x: -x["investment_score"])}
