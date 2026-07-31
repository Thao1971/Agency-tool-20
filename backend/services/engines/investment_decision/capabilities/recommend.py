"""Recomendaciones automáticas (POST /recommendations). Rankea un universo de oportunidades
para un perfil de comprador combinando el score del comité (proactivo, explicable). Determinista."""

from typing import Dict, List
from services.engines.investment_decision import engine as IDE


def _key(item: Dict) -> str:
    return item.get("opportunity_id") or item.get("company_id") or item.get("cif") or "op"


async def recommend(buyer_profile: Dict, universe: List[Dict]) -> Dict:
    if not universe:
        return {"status": "insufficient_data",
                "note": "Aporta un 'universe' de oportunidades (company_id/cif) para rankear.",
                "buyer_profile": (buyer_profile or {}).get("type"), "items": []}
    items = []
    for it in universe:
        req = {"opportunity_id": _key(it), "company_id": it.get("company_id"),
               "cif": it.get("cif"), "buyer_profile": buyer_profile, "inputs": it.get("inputs") or {}}
        r = await IDE.analyze(req)
        rationale = [f.get("text") for f in (r.get("strengths") or [])[:3] if f.get("text")]
        items.append({"opportunity_id": _key(it),
                      "fit_score": round(r["investment_score"] / 100, 4),
                      "predicted_recommendation": r["recommendation"],
                      "confidence": r["confidence"], "rationale": rationale})
    return {"status": "ok", "buyer_profile": (buyer_profile or {}).get("type"),
            "items": sorted(items, key=lambda x: -x["fit_score"])}
