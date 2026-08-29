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

# HARDENING-038e · La narrativa IA (prosa florida) es el ÚNICO paso lento del comité: el
# veredicto determinista —score/banda/10 opiniones/razonamiento— ya está completo antes.
# En vez de bloquear la respuesta con un cap corto, analyze() devuelve el veredicto al
# INSTANTE y genera la prosa en SEGUNDO PLANO, cacheándola por decision_id (mismo
# veredicto ⇒ mismo id ⇒ en el siguiente clic la prosa ya está lista). La librería LLM
# bloquea el event loop, así que la generación se descarga a un hilo (loop principal libre).
_NARRATIVE_BG_TIMEOUT_S: float = float(os.environ.get("IDE_NARRATIVE_BG_TIMEOUT_S", "120"))

# Guarda en proceso: evita lanzar dos generaciones IA a la vez para el mismo decision_id.
_narrative_inflight: set = set()


def _narrative_enabled() -> bool:
    """La IA solo se invoca si el provider elegido tiene su clave (si no, prosa determinista)."""
    return bool(os.environ.get(_PROVIDER_KEY.get(NARRATIVE_PROVIDER, "")))


async def _generate_narrative(consensus: Dict, profile: Dict) -> Dict:
    """Genera la prosa IA (fact-lock) SIN cap corto. La librería LLM bloquea el event loop,
    así que se descarga a un hilo con su propio loop (loop principal libre); una red de
    seguridad amplia evita hilos colgados para siempre. Devuelve el dict de la IA o {}."""
    from docstudio.model_provider import generate_summary
    ctx = P.narrative_context(consensus, profile)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(lambda: asyncio.run(
                generate_summary(ctx, doc_type="investment_decision",
                                 provider=NARRATIVE_PROVIDER, fact_lock=True))),
            timeout=_NARRATIVE_BG_TIMEOUT_S,
        ) or {}
    except Exception:
        return {}


def _apply_narrative(consensus: Dict, ai: Dict) -> bool:
    """Aplica la prosa IA al consenso in-place (solo executive_summary / investment_thesis;
    NUNCA toca score, banda, comité ni razonamiento). Devuelve True si se aplicó."""
    if ai.get("executive_summary") and "error" not in ai and "raw_text" not in ai:
        consensus["executive_summary"] = ai["executive_summary"]
        if ai.get("conclusion"):
            consensus["investment_thesis"] = ai["conclusion"]
        consensus["meta"]["narrative_ai"] = True
        return True
    return False


async def _bg_narrative(record: Dict, profile: Dict) -> None:
    """Tarea en segundo plano: genera la prosa IA (sin cap) y actualiza la decisión
    almacenada → cache por decision_id para el siguiente clic. Best-effort, nunca lanza."""
    did = record["decision_id"]
    consensus = record["result"]
    try:
        ai = await _generate_narrative(consensus, profile)
        consensus["meta"]["narrative_status"] = "ready" if _apply_narrative(consensus, ai) else "failed"
        await store.save({**record, "result": consensus})
    except Exception:
        pass
    finally:
        _narrative_inflight.discard(did)


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
        "narrative_provider": NARRATIVE_PROVIDER, "narrative_ai": False,
    }

    # 4. Prosa IA (Fase 6, fact-lock) — NO altera números ni banda. Veredicto INSTANTÁNEO:
    #    (a) si ya hay prosa cacheada para este decision_id (mismo veredicto), se sirve al
    #    instante; (b) si no, se devuelve la prosa determinista YA y la IA se genera en
    #    SEGUNDO PLANO y se cachea por decision_id (Beta sondea GET /decision/{id} hasta
    #    narrative_status=="ready").
    record = {"decision_id": did, "opportunity_id": request.get("opportunity_id"),
              "buyer_profile": profile["type"], "result": consensus, "created_at": now_iso()}
    cres = ((await store.get(did)) or {}).get("result") or {}
    if cres.get("meta", {}).get("narrative_ai") and cres.get("executive_summary"):
        consensus["executive_summary"] = cres["executive_summary"]
        consensus["investment_thesis"] = cres.get("investment_thesis", consensus["investment_thesis"])
        consensus["meta"]["narrative_ai"] = True
        consensus["meta"]["narrative_status"] = "cached"
    elif _narrative_enabled():
        consensus["meta"]["narrative_status"] = "generating"
        await store.save(record)
        if did not in _narrative_inflight:
            _narrative_inflight.add(did)
            asyncio.create_task(_bg_narrative(record, profile))
    else:
        consensus["meta"]["narrative_status"] = "deterministic"
        await store.save(record)
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
