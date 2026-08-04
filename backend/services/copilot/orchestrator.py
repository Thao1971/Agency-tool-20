"""Router del Copilot — enruta por nivel (L0–L4), fusiona y devuelve UN resultado para la voz.
Determinista. Reutiliza evidencia, especialistas, comité y capacidades ya existentes (no recrea)."""

import time
from typing import Dict, List
from services.copilot import ORCHESTRATOR_VERSION
from services.copilot import intent as INTENT
from services.copilot import metrics as METRICS
from services.copilot import memory as MEMORY
from services.copilot import session as SESSION
from services.copilot import voice as VOICE
from services.copilot import entity_memory as ENTITY
from services.copilot import feedback as FEEDBACK
from services.copilot import narrator as NARRATOR
from services.copilot import actions as ACTIONS
from services.copilot import proactivity as PROACTIVITY
from services.engines.investment_decision import evidence as EV
from services.engines.investment_decision import engine as IDE
from services.engines.investment_decision import models as M
from services.engines.investment_decision.committee import build_committee
from services.engines.investment_decision.capabilities import (
    compare as cap_compare, portfolio as cap_portfolio, recommend as cap_recommend)

_SPECIALISTS = {sp.name: sp for sp in build_committee()}

_METRIC_FMT = {
    "revenue": ("Ingresos", lambda v: f"{v:,.0f} €".replace(",", ".")),
    "ebitda": ("EBITDA", lambda v: f"{v:,.0f} €".replace(",", ".")),
    "ebitda_margin": ("Margen EBITDA", lambda v: f"{v*100:.1f} %".replace(".", ",")),
    "revenue_cagr": ("CAGR de ingresos", lambda v: f"{v*100:+.1f} %".replace(".", ",")),
    "revenue_per_employee": ("Ingresos por empleado", lambda v: f"{v:,.0f} €".replace(",", ".")),
    "solvency": ("Autonomía financiera", lambda v: f"{v*100:.0f} %"),
    "employees": ("Empleados", lambda v: f"{int(v):,}".replace(",", ".")),
    "net_debt": ("Deuda financiera neta", lambda v: f"{v:,.0f} €".replace(",", ".")),
}


def _result(level, cim_state, answer, sources, **extra):
    out = {"orchestrator_version": ORCHESTRATOR_VERSION, "level": level,
           "cim_state": cim_state, "answer": answer, "sources": sources}
    out.update(extra)
    return out


def _fact(bundle, metric):
    kp = bundle.get("kpis") or {}
    pts = sorted([p for p in ((bundle.get("evolution") or {}).get("points") or []) if p.get("year")],
                 key=lambda x: x["year"])
    last = pts[-1] if pts else {}
    val = kp.get(metric)
    if val is None and metric == "net_debt":
        val = last.get("net_financial_position")
    if val is None and metric == "employees":
        val = (bundle.get("financials") or {}).get("employees")
    return val


async def orchestrate(request: Dict) -> Dict:
    """Envoltorio con memoria de usuario + sesión (Fase 1). Carga perfil por defecto, reanuda/abre
    sesión, resuelve referencias implícitas (entidad activa), enruta y persiste el turno. La memoria
    solo personaliza qué/tono/prioridades; NUNCA cambia hechos ni scores del comité."""
    t0 = time.time()
    user = request.get("user") or {}
    tenant_id, user_id = user.get("tenant_id"), user.get("user_id")
    umem = await MEMORY.get_user_memory(tenant_id, user_id)

    # Perfil efectivo: petición > memoria de usuario > default
    bp_req = (request.get("buyer_profile") or {}).get("type")
    bp_source = "request" if bp_req else ("user_memory" if umem.get("buyer_profile") else "default")
    profile_type = M.buyer_profile(bp_req or umem.get("buyer_profile"))["type"]

    # Sesión + continuidad de referencias
    sess = await SESSION.get_or_create(request.get("session_id"), tenant_id, user_id,
                                       {"type": profile_type})
    session_id = sess["session_id"]
    active = (sess.get("working_context") or {}).get("active_entity") or {}
    history = (sess.get("turns") or [])[-6:]      # turnos PREVIOS (sin el actual) → contexto conversacional

    req = dict(request)
    req["buyer_profile"] = {"type": profile_type}
    if not (req.get("company_id") or req.get("cif") or req.get("opportunity_id")) and active.get("id"):
        req["company_id"] = active["id"]
        req["opportunity_id"] = active["id"]
        if active.get("cif"):
            req["cif"] = active["cif"]

    # Entity linking desde texto libre (Boundary First: reutiliza el resolver canónico de Company
    # Intelligence; el Copilot NUNCA busca en master_companies). Solo si no hay id explícito ni
    # entidad activa. Se aplica a intents de una sola empresa (L0–L3) y a L4 'peers' (necesita
    # sujeto); NO a taxo_search/compare/portfolio/recommend. Nunca ejecuta el comité con entidad ambigua.
    _intent = INTENT.classify(request.get("question") or "", request.get("screen"))
    _needs_entity = _intent["level"] != "L4" or _intent.get("capability") == "peers"
    if _needs_entity and not (
            req.get("company_id") or req.get("cif") or req.get("opportunity_id")):
        from services.copilot import entity_link as LINK
        linked = await LINK.link(request.get("question"))
        if linked["status"] == "resolved":
            e = linked["entity"]
            req["company_id"] = e["master_id"]
            req["cif"] = e.get("cif")
            req["opportunity_id"] = e["master_id"]
        elif linked["status"] == "ambiguous":
            mention = linked.get("mention") or "esa compañía"
            names = ", ".join(c["name"] for c in linked["candidates"][:3])
            msg = (f"He encontrado varias compañías que podrían corresponder a «{mention}»: {names}. "
                   f"¿A cuál te refieres?")
            actions = [{"id": f"pick_{i}", "kind": "select_entity",
                        "label": f"{c['name']}" + (f" — {c['cif']}" if c.get("cif") else ""),
                        "params": {"company_id": c["master_id"], "name": c["name"]}}
                       for i, c in enumerate(linked["candidates"][:5])]
            out = {"orchestrator_version": ORCHESTRATOR_VERSION, "level": "L0",
                   "cim_state": "conversation", "sources": ["company-intelligence"],
                   "disambiguation": True, "session_id": session_id,
                   "answer": {"headline": "¿A cuál te refieres?", "message": msg, "detail": msg},
                   "actions": actions,
                   "personalization_applied": {"buyer_profile": profile_type,
                                               "buyer_profile_source": bp_source}}
            await SESSION.update(session_id,
                                 context_patch={"pending_disambiguation": linked["candidates"]},
                                 turn={"user_text": request.get("question"), "level": "L0",
                                       "entity": None, "summary": "Desambiguación de entidad"})
            await METRICS.record_turn({"tenant_id": tenant_id, "user_id": user_id,
                                       "session_id": session_id, "level": "L0",
                                       "kind": "disambiguation", "degraded": False,
                                       "response_ms": round((time.time() - t0) * 1000, 1),
                                       "buyer_profile": profile_type})
            return out

    # Sesgo de ranking aprendido (solo surfacing) + dimensiones de las oportunidades para aplicarlo.
    rank_bias = await FEEDBACK.compute_bias(tenant_id, user_id)
    dims_by_key: Dict = {}
    for it in (request.get("opportunities") or []) + (request.get("universe") or []):
        k = it.get("opportunity_id") or it.get("company_id") or it.get("cif")
        if k:
            dims_by_key[k] = FEEDBACK.dims_from_inputs(it.get("inputs") or {})
    req["_rank_bias"], req["_dims_by_key"] = rank_bias, dims_by_key

    sink: Dict = {}
    try:
        out = await _route(req, sink)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("copilot _route failed")
        _msg = ("No he podido completar el análisis en este momento. Vuelve a intentarlo en unos "
                "segundos y, si persiste, dímelo y lo reviso.")
        out = {"orchestrator_version": ORCHESTRATOR_VERSION, "level": "L0",
               "cim_state": "conversation", "sources": [], "degraded": True,
               "answer": {"headline": "No he podido completar el análisis.",
                          "message": _msg, "detail": _msg}}

    # Memoria de entidad (ANTES de narrar, para poder contar la evolución en L3). En L3 archiva la
    # decisión y calcula el diff; en otros niveles adjunta el último análisis si ya existe.
    ent = sink.get("entity")
    if ent and ent.get("id") and tenant_id and user_id:
        dec = out.get("decision") or {}
        if out.get("level") == "L3" and dec.get("recommendation"):
            out["entity_history"] = await ENTITY.record_decision(
                tenant_id, user_id, ent["id"], dec)
        else:
            prev = await ENTITY.latest(tenant_id, user_id, ent["id"])
            if prev:
                out["entity_history"] = {"previous": prev,
                                         "narrative": ENTITY.latest_narrative(prev)}

    # Voz: rol (petición > memoria) + autonomía → verbosidad/tono + estado CIM máximo proactivo.
    role = user.get("role") or umem.get("role")
    directives = VOICE.resolve(role, umem.get("autonomy_level"))
    out["voice"] = directives

    # Narración + NBA solo si el análisis se completó (en degradado, se mantiene el mensaje de error).
    if not out.get("degraded"):
        nctx = {"name": (ent or {}).get("name") or "la compañía", "profile": profile_type,
                "role": role, "verbosity": directives["verbosity"],
                "entity_history": out.get("entity_history"),
                "ranking_bias": FEEDBACK.summarize(rank_bias), "history": history,
                "entities": INTENT.extract_entities(request.get("question") or "")}
        nat = await NARRATOR.narrate(out, nctx)
        ans = out.get("answer") or {}
        ans["headline"], ans["message"], ans["detail"] = nat["headline"], nat["message"], nat["message"]
        if nat.get("disclosure"):
            ans["disclosure"] = nat["disclosure"]  # banda/score/confianza para "ver deliberación"
        if nat.get("attribution"):
            ans["attribution"] = nat["attribution"]  # áreas que intervinieron (citar capabilities)
        out["answer"] = ans
        VOICE.apply_verbosity(ans, directives)

        name = (ent or {}).get("name")
        resolved = bool(ent and ent.get("id")) and bool(name) and name != "la compañía"
        nba = ACTIONS.build(out, {"name": name or "la compañía", "entity_id": (ent or {}).get("id"),
                                  "resolved": resolved, "autonomy_level": directives["autonomy_level"],
                                  "bias": FEEDBACK.summarize(rank_bias), "profile": profile_type})
        if nba.get("card"):
            out["ui"] = {"card": nba["card"]}
        out["actions"] = nba.get("actions") or []

        # Autonomía proactiva: un nudge si el Copilot ha notado algo relevante (gobernado por autonomía).
        prox = PROACTIVITY.build(out, {
            "autonomy_level": directives["autonomy_level"], "name": (ent or {}).get("name"),
            "entity_history": out.get("entity_history"),
            "coverage": ((out.get("decision") or {}).get("reasoning") or {}).get("coverage")})
        if prox:
            out["proactive"] = prox

    # Enriquecer con sesión + transparencia de personalización
    out["session_id"] = session_id
    out["personalization_applied"] = {
        "memory_scope": "user", "buyer_profile": profile_type, "buyer_profile_source": bp_source,
        "role": role, "verbosity": directives["verbosity"],
        "autonomy_level": directives["autonomy_level"],
        "max_proactive_state": directives["max_proactive_state"],
        "ranking_bias": FEEDBACK.summarize(rank_bias),
        "context_turns": len(history),
        "reference_resolved": bool(active.get("id")) and not (
            request.get("company_id") or request.get("cif") or request.get("opportunity_id"))}

    # Persistir contexto + turno
    ctx: Dict = {"last_level": out.get("level")}
    if ent and ent.get("id"):
        ctx["active_entity"] = ent
    if (out.get("decision") or {}).get("decision_id"):
        ctx["last_decision_id"] = out["decision"]["decision_id"]
    await SESSION.update(session_id, context_patch=ctx,
                         turn={"user_text": req.get("question"), "level": out.get("level"),
                               "entity": ent or None,
                               "summary": (out.get("answer") or {}).get("headline")})

    # Observabilidad: métrica compacta del turno (best-effort; solo señales, sin contenido).
    await METRICS.record_turn({
        "tenant_id": tenant_id, "user_id": user_id, "session_id": session_id,
        "level": out.get("level"), "capability": out.get("capability"),
        "kind": (out.get("decision") and "decision") or None,
        "degraded": bool(out.get("degraded")),
        "response_ms": round((time.time() - t0) * 1000, 1),
        "coverage": ((out.get("decision") or {}).get("reasoning") or {}).get("coverage"),
        "n_actions": len(out.get("actions") or []),
        "had_card": bool((out.get("ui") or {}).get("card")),
        "buyer_profile": profile_type})
    return out


async def _route(request: Dict, _sink: Dict = None) -> Dict:
    text = request.get("question") or request.get("text") or ""
    screen = request.get("screen")
    profile = M.buyer_profile((request.get("buyer_profile") or {}).get("type"))
    intent = request.get("force_intent") or INTENT.classify(text, screen)
    level = intent["level"]

    # L4 — capacidades (compare / portfolio / recommend / peers / taxo_search)
    if level == "L4":
        cap = intent["capability"]
        bp = request.get("buyer_profile") or {"type": profile["type"]}
        # Taxonomía ARROBA: comparables (peers), búsqueda por sector/vertical y comparación de pares.
        if cap in ("peers", "taxo_search", "compare_pair"):
            cid = request.get("company_id") or request.get("cif") or request.get("opportunity_id")
            try:
                from services.taxonomy import similarity as _SIM
                from services.taxonomy import search as _SR
                if cap == "peers":
                    data = await _SIM.peers(cid, k=int(request.get("k") or 8)) if cid else \
                        {"peers": [], "note": "Dime sobre qué compañía busco comparables."}
                elif cap == "compare_pair":
                    b = None
                    if request.get("company_id_b"):
                        b = {"company_id": request["company_id_b"], "name": request["company_id_b"]}
                    else:
                        for e in INTENT.extract_entities(text):
                            hit = await _SR.resolve_company_by_name(e)
                            if hit and hit["company_id"] != cid:
                                b = hit
                                break
                    if cid and b:
                        data = await _SIM.compare_pair(cid, b["company_id"])
                        data["b_name"] = b.get("name")
                    else:
                        data = {"note": "Dime las dos compañías a comparar (analiza una y nómbrame la otra)."}
                else:
                    hit = _SR.resolve_label(text)
                    if not hit:
                        data = {"count": 0, "company_ids": [], "note": "No reconozco ese sector/vertical."}
                    else:
                        node = hit["id"] if hit["kind"] in _SR._IS_NODE else None
                        dim = None if node else hit["id"]
                        data = await _SR.search_by_taxonomy(node_id=node, dimension_id=dim, limit=10)
                        data["label"] = hit["label"]
            except Exception:
                data = {"peers": [], "company_ids": [], "note": "La taxonomía no está disponible ahora."}
            return _result("L4", "recommender",
                           {"headline": f"Capacidad: {cap}", "detail": "", "data": data},
                           sources=["arroba-company-taxonomy-v1"], capability=cap)
        if cap == "compare":
            r = await cap_compare.compare(request.get("opportunities") or [], bp)
        elif cap == "portfolio":
            r = await cap_portfolio.portfolio(request.get("opportunities") or [], bp)
        else:
            r = await cap_recommend.recommend(bp, request.get("universe") or [])
        # Sesgo aprendido: reordena el surfacing (NUNCA el score del comité).
        bias = request.get("_rank_bias") or {}
        dims = request.get("_dims_by_key") or {}
        if bias:
            if cap == "compare" and r.get("ranking"):
                r["ranking"] = FEEDBACK.rank_with_bias(
                    r["ranking"], "opportunity_id", "investment_score", 100, dims, bias)
            elif cap == "recommend" and r.get("items"):
                r["items"] = FEEDBACK.rank_with_bias(
                    r["items"], "opportunity_id", "fit_score", 1, dims, bias)
        return _result("L4", "recommender",
                       {"headline": f"Capacidad: {cap}", "detail": "", "data": r},
                       sources=["investment-decision-engine-v1"], capability=cap)

    # A partir de aquí necesitamos evidencia de una compañía
    resolved = await EV.resolve_evidence(request)
    bundle = resolved["bundle"]
    name = (bundle.get("identity") or {}).get("name") or "la compañía"
    if _sink is not None:
        _sink["entity"] = {"id": request.get("company_id") or request.get("opportunity_id")
                           or request.get("cif"), "name": name,
                           "cif": bundle.get("cif_normalized") or request.get("cif")}

    # L3 — comité completo
    if level == "L3":
        consensus = await IDE.analyze(request)
        ans = {"headline": f"Recomendación del comité: {consensus['recommendation']} "
                           f"({consensus['investment_score']}/100)",
               "detail": consensus.get("executive_summary"), "data": None}
        return _result("L3", "recommender", ans,
                       sources=["investment-decision-engine-v1"], committee=consensus.get("committee"),
                       decision=consensus)

    # L0 — hecho / overview  (adjunta datos estructurados para que el narrador redacte natural)
    if level == "L0":
        metric = intent["metric"]
        if metric == "__overview__":
            facts = []
            for mk in ("revenue", "ebitda", "ebitda_margin", "employees"):
                v = _fact(bundle, mk)
                if v is not None:
                    lbl, fmt = _METRIC_FMT[mk]
                    facts.append({"label": lbl, "value": fmt(v)})
            detail = " · ".join(f"{f['label']}: {f['value']}" for f in facts) or \
                "No dispongo de datos financieros suficientes."
            return _result("L0", "conversation",
                           {"headline": f"{name} — resumen", "detail": detail},
                           resolved["engines_used"], subject=name, facts=facts)
        v = _fact(bundle, metric)
        lbl, fmt = _METRIC_FMT.get(metric, (metric, str))
        if v is None:
            return _result("L0", "conversation",
                           {"headline": lbl, "detail": f"No consta {lbl.lower()} en el dato disponible."},
                           resolved["engines_missing"], unsupported=True, subject=name,
                           fact={"label": lbl, "value": None, "available": False, "metric": metric})
        return _result("L0", "conversation",
                       {"headline": lbl, "detail": f"{lbl} de {name}: {fmt(v)}."},
                       ["financial-intelligence"], subject=name,
                       fact={"label": lbl, "value": fmt(v), "available": True, "metric": metric})

    # L1 / L2 — especialista(s)
    targets = [t for t in intent["targets"] if t in _SPECIALISTS] or ["cfo"]
    ops = [_SPECIALISTS[t].evaluate(bundle, profile) for t in targets]
    ops = [o for o in ops if o.get("recommendation") != M.REC_ABSTAIN] or ops
    # Fusión a una sola voz
    def _texts(o):
        out = []
        for k in ("strengths", "risks"):
            out += [f.get("text") for f in (o.get(k) or []) if isinstance(f, dict) and f.get("text")]
        out += [c for c in (o.get("conditions") or []) if isinstance(c, str)]
        return out
    detail = " ".join(t for o in ops for t in _texts(o)[:2])[:600] or "Sin lectura concluyente con el dato disponible."
    conflict = len({o["recommendation"] for o in ops}) > 1
    src = sorted({e["engine"] for o in ops for e in (o.get("evidence") or [])})
    ans = {"headline": f"{name} — {', '.join(targets)}", "detail": detail,
           "conflict": conflict}
    extra = {}
    if conflict:
        ans["detail"] += "  (Las áreas no coinciden del todo; para una decisión conviene convocar al comité.)"
        extra["suggest_escalation"] = "L3"
    return _result(level, "recommender" if any(o.get("conditions") for o in ops) else "conversation",
                   ans, src or resolved["engines_used"], opinions=ops, targets=targets,
                   subject=name, **extra)
