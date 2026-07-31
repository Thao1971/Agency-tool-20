"""Comparación de oportunidades (POST /compare). Ejecuta el análisis de N oportunidades con el
mismo perfil de comprador y devuelve ranking + matriz comité×oportunidad. Determinista."""

from typing import Dict, List
from services.engines.investment_decision import engine as IDE


def _key(item: Dict) -> str:
    return item.get("opportunity_id") or item.get("company_id") or item.get("cif") or "op"


async def compare(opportunities: List[Dict], buyer_profile: Dict) -> Dict:
    results = []
    for it in opportunities or []:
        req = {"opportunity_id": _key(it), "company_id": it.get("company_id"),
               "cif": it.get("cif"), "buyer_profile": buyer_profile, "inputs": it.get("inputs") or {}}
        r = await IDE.analyze(req)
        results.append((_key(it), r))

    ranking = sorted(
        [{"opportunity_id": k, "investment_score": r["investment_score"],
          "recommendation": r["recommendation"], "confidence": r["confidence"]}
         for k, r in results],
        key=lambda x: -x["investment_score"])

    # Matriz comité × oportunidad (score por especialista; None si se abstiene)
    matrix: Dict[str, Dict] = {}
    for k, r in results:
        for o in r["committee"]:
            matrix.setdefault(o["specialist"], {})[k] = o.get("score")

    return {"buyer_profile": (buyer_profile or {}).get("type"),
            "ranking": ranking, "matrix": matrix,
            "opportunities_analyzed": [k for k, _ in results]}
