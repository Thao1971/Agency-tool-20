"""Orquestador del Investment Decision Engine — analyze() (DESIGN §4).
Determinista: misma entrada ⇒ mismo score, banda y decision_id."""

import os
import asyncio
from typing import Dict, List
from models import now_iso
from services.engines.investment_decision import ENGINE_VERSION, models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision import evidence as EV
from services.engines.investment_decision import consensus as C
from services.engines.investment_decision import store
from services.engines.investment_decision import prompts as P
from services.engines.investment_decision.committee import build_committee

# Provider de la narrativa (Fase 6). Config por entorno: claude (calidad) | nvidia (coste) | openai.
NARRATIVE_PROVIDER = os.environ.get("IDE_NARRATIVE_PROVIDER", "claude")
_PROVIDER_KEY = {"claude": "EMERGENT_LLM_KEY", "openai": "EMERGENT_LLM_KEY", "nvidia": "NVIDIA_API_KEY"}

# HARDENING-038d · La narrativa IA es el ÚNICO paso lento del comité (el veredicto
# determinista —score/banda/10 opiniones/razonamiento— ya está completo antes). Con
# cap corto, analyze() responde por debajo del cap del proxy de Beta (7.5s) y del edge
# (~8s): si el LLM no entra en presupuesto, se mantiene la prosa determinista (el
# comité SIGUE mostrando su veredicto real en el primer clic).
_NARRATIVE_TIMEOUT_S: float = float(os.environ.get("IDE_NARRATIVE_TIMEOUT_S", "4.0"))


def _narrative_enabled() -> bool:
    """La IA solo se invoca si el provider elegido tiene su clave (si no, prosa determinista)."""
    return bool(os.environ.get(_PROVIDER_KEY.get(NARRATIVE_PROVIDER, "")))


async def _apply_ai_narrative(consensus: Dict, profile: Dict) -> Dict:
    """Fase 6 — redacción fact-lock. Solo reescribe executive_summary / investment_thesis a partir
    de la decisión YA tomada; NUNCA toca score, banda, comité ni razonamiento. Best-effort."""
    consensus["meta"]["narrative_provider"] = NARRATIVE_PROVIDER
    consensus["meta"]["narrative_ai"] = False
    if not _narrative_enabled():
        return consensus
    try:
        from docstudio.model_provider import generate_summary
        ctx = P.narrative_context(consensus, profile)
        # La librería LLM (emergentintegrations) BLOQUEA el event loop pese a ser `async`
        # (medido: wait_for(4s) directo sobre la corrutina tardaba ~17s en cortar). Se
        # descarga a un hilo con su propio loop → el loop principal queda LIBRE y el cap
        # de _NARRATIVE_TIMEOUT_S corta de verdad en presupuesto. Si el LLM no entra a
        # tiempo, salta TimeoutError (capturado abajo) y se mantiene la prosa determinista.
        ai = await asyncio.wait_for(
            asyncio.to_thread(lambda: asyncio.run(
                generate_summary(ctx, doc_type="investment_decision",
                                 provider=NARRATIVE_PROVIDER, fact_lock=True))),
            timeout=_NARRATIVE_TIMEOUT_S,
        ) or {}
        if ai.get("executive_summary") and "error" not in ai and "raw_text" not in ai:
            consensus["executive_summary"] = ai["executive_summary"]
            if ai.get("conclusion"):
                consensus["investment_thesis"] = ai["conclusion"]
            consensus["meta"]["narrative_ai"] = True
    except Exception:
        pass  # degradación limpia: se mantiene la prosa determinista
    return consensus


async def analyze(request: Dict) -> Dict:
    profile = M.buyer_profile((request.get("buyer_profile") or {}).get("type"),
                              (request.get("buyer_profile") or {}).get("mandate"),
                              (request.get("buyer_profile") or {}).get("capacity_eur"))

    resolved = await EV.resolve_evidence(request)
    bundle = resolved["bundle"]
    bundle_name = (bundle.get("identity") or {}).get("name")

    # 1. Comité (determinista, orden estable)
    weights = S.apply_buyer_profile(S.COMMITTEE_WEIGHTS, profile["type"])
    opinions: List[Dict] = []
    for sp in build_committee():
        op = sp.evaluate(bundle, profile)
        # Salvaguarda de trazabilidad: ninguna conclusión sin evidencia ⇒ se abstiene.
        if op.get("recommendation") != M.REC_ABSTAIN and not op.get("evidence"):
            op = sp._abstain("Sin evidencia suficiente para emitir opinión.")
        op["weight_base"] = S.COMMITTEE_WEIGHTS.get(sp.name, 0.0)
        op["weight_applied"] = weights.get(sp.name, 0.0)
        opinions.append(op)

    # 2. Agregación
    score01 = S.committee_score(opinions, weights)
    disp = S.dispersion(opinions)
    vetoes = [o for o in opinions if o.get("veto")]
    conf = S.confidence(coverage=resolved["coverage"], data_quality=resolved["coverage"],
                        cross_engine_consistency=round(1.0 - disp, 4), recency=0.8,
                        committee_agreement=round(1.0 - disp, 4))
    score100 = int(round(score01 * 100))
    band = S.decide_band(score100, conf["value"], disp, vetoes, resolved["coverage"])

    # 3. Consenso
    ev_meta = {**{k: resolved[k] for k in ("coverage", "engines_used", "engines_missing")},
               "bundle_name": bundle_name}
    consensus = C.build_consensus(opinions, weights, score100, conf, band, disp, vetoes, ev_meta, profile)

    did = store.decision_id(request.get("opportunity_id") or bundle.get("master_id") or "unknown",
                            profile["type"], resolved["engines_used"], band, score100)
    consensus["meta"] = {
        "engine_version": ENGINE_VERSION, "decision_id": did,
        "buyer_profile": profile["type"], "generated_at": now_iso(),
        "deterministic": True, "source": resolved["source"],
        "status": ("insufficient_data" if resolved["coverage"] < S.MIN_COVERAGE else "ok"),
    }
    # 4. Capa narrativa (Fase 6, fact-lock) — no altera números ni banda
    consensus = await _apply_ai_narrative(consensus, profile)

    await store.save({"decision_id": did, "opportunity_id": request.get("opportunity_id"),
                      "buyer_profile": profile["type"], "result": consensus,
                      "created_at": now_iso()})
    return consensus


async def committee_only(request: Dict) -> List[Dict]:
    """Solo el array de opiniones (rápido, sin consenso)."""
    profile = M.buyer_profile((request.get("buyer_profile") or {}).get("type"))
    resolved = await EV.resolve_evidence(request)
    weights = S.apply_buyer_profile(S.COMMITTEE_WEIGHTS, profile["type"])
    out = []
    for sp in build_committee():
        op = sp.evaluate(resolved["bundle"], profile)
        op["weight_applied"] = weights.get(sp.name, 0.0)
        out.append(op)
    return out
