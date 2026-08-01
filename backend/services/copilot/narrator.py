"""ARROBA Copilot — narrador (Natural Executive Conversation, copilot-voice-v1).

Convierte la evidencia YA calculada (hechos, opiniones del especialista, consenso del comité, histórico
de entidad, sesgo de ranking) en prosa ejecutiva, ágil y natural — como un copiloto senior de M&A.
Determinista y FACT-LOCK: la naturalidad viene de explicar mejor la evidencia disponible, nunca de
rellenar huecos ni cambiar el score del comité. Pulido por IA opcional (COPILOT_VOICE_PROVIDER) que solo
REESCRIBE el borrador. Ver memory/ARROBA_COPILOT_VOICE_NATURAL_EXECUTIVE.md.
"""

import json
import os
import re
from typing import Dict, List

NARRATOR_VERSION = "copilot-voice-v1"


def _introduces_new_numbers(ai_msg: str, allowed_text: str) -> bool:
    """Guardián fact-lock en runtime: True si el texto de la IA contiene un número (≥2 dígitos) cuyos
    dígitos NO aparecen en el borrador/evidencia permitidos. Lenient (compara por subcadena de dígitos)
    para no rechazar reformateos legítimos, pero atrapa cifras inventadas."""
    allowed = re.sub(r"\D", "", allowed_text or "")
    for tok in re.findall(r"\d[\d.,]*", ai_msg or ""):
        d = re.sub(r"\D", "", tok)
        if len(d) >= 2 and d not in allowed:
            return True
    return False

# Recomendación del comité (banda interna) → frase natural. El usuario habla con UNA voz (el Copilot);
# la banda/score son internos y NO se muestran en el chat (van en `disclosure` → "ver deliberación").
_REC_PHRASE = {
    "PROCEED": "Yo avanzaría con esta operación",
    "PROCEED_WITH_CONDITIONS": "Avanzaría, pero sujeto a condiciones",
    "EXPLORE": "La mantendría en el radar y la exploraría con cautela",
    "PASS": "Por ahora no la priorizaría",
    "REJECT": "La descartaría",
}
# Evolución entre análisis, en cualitativo (sin números en la frase).
_EVO_ES = {"improved": "Frente a nuestra última revisión, el caso ha mejorado.",
           "worsened": "Frente a nuestra última revisión, el caso ha perdido atractivo.",
           "stable": "Se mantiene en línea con nuestra última revisión."}


def conviction_label(score) -> str:
    """Etiqueta corta de convicción para el chip/'ver deliberación'."""
    if score is None:
        return "Sin valorar"
    if score >= 80:
        return "Convicción alta"
    if score >= 65:
        return "Convicción sólida"
    if score >= 55:
        return "Convicción moderada"
    if score >= 45:
        return "Con reservas"
    return "Baja convicción"


def _conviction_phrase(score) -> str:
    return {"Convicción alta": "con convicción alta", "Convicción sólida": "con bastante convicción",
            "Convicción moderada": "con convicción moderada", "Con reservas": "con reservas",
            "Baja convicción": "con poca convicción", "Sin valorar": ""}[conviction_label(score)]

# Frases de due diligence por dominio cuando NO hay evidencia concluyente (marcos estándar, presentados
# como "a validar", nunca como hechos de la compañía).
_DD_FRAMES = {
    "risk": "concentración de clientes, recurrencia de ingresos y sostenibilidad de márgenes",
    "commercial": "concentración de clientes, recurrencia de ingresos y coste de adquisición",
    "cfo": "calidad de los earnings, conversión en caja y necesidades de circulante",
    "valuation": "múltiplo de referencia, perímetro y ajustes de deuda a equity",
    "market": "posición competitiva, poder de fijación de precios y dinámica de consolidación",
    "operations": "escalabilidad, dependencia de personas clave y eficiencia operativa",
    "hr": "continuidad del equipo directivo y plan de sucesión",
    "strategy": "encaje estratégico y sinergias realizables",
    "legal": "estructura de propiedad, contingencias y contratos críticos",
}
_DOMAIN_ES = {"risk": "los riesgos", "valuation": "la valoración", "market": "el mercado",
              "cfo": "la situación financiera", "commercial": "la parte comercial",
              "operations": "la operativa", "hr": "el equipo", "strategy": "el encaje estratégico",
              "legal": "la parte legal/societaria"}


def _area_label(name: str) -> str:
    try:
        from services.engines.investment_decision.committee import capabilities as CAP
        return CAP.CAPABILITIES.get(name, {}).get("label", name)
    except Exception:
        return name


def _text(x):
    return x.get("text") if isinstance(x, dict) else (x if isinstance(x, str) else None)


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " y " + items[-1]


def _lower_first(s: str) -> str:
    if not s:
        return s
    first = s.split(" ", 1)[0]
    if first.isupper() and len(first) > 1:      # acrónimo (EBITDA, CAGR…): no tocar
        return s
    return s[0].lower() + s[1:]


def _clean(t: str) -> str:
    return t.rstrip(" .").strip() if isinstance(t, str) else t


def _texts(op: Dict, key: str) -> List[str]:
    return [_clean(t) for t in (_text(f) for f in (op.get(key) or [])) if t]


# ---------- L0: hechos ----------
def _n_fact(out: Dict, ctx: Dict) -> Dict:
    name = ctx["name"]
    facts = out.get("facts")
    if facts:
        parts = [f"{_lower_first(f['label'])} de {f['value']}" for f in facts]
        msg = f"En síntesis, {name} presenta {_join(parts)}."
        return {"headline": f"Radiografía rápida de {name}.", "message": msg}
    fact = out.get("fact") or {}
    label = fact.get("label", "el dato")
    if fact.get("available"):
        msg = f"El {_lower_first(label)} de {name} es de {fact.get('value')}."
        return {"headline": msg, "message": msg}
    msg = (f"Aún no tengo cargado {_lower_first(label)} de {name}; en cuanto entre el dato te lo doy "
           f"al momento.")
    return {"headline": f"{label} — pendiente de dato.", "message": msg}


# ---------- L1/L2: especialista(s) ----------
def _n_specialist(out: Dict, ctx: Dict) -> Dict:
    name = ctx["name"]
    ops = out.get("opinions") or []
    targets = out.get("targets") or []
    domain = targets[0] if targets else None
    risks = [t for o in ops for t in _texts(o, "risks")]
    strengths = [t for o in ops for t in _texts(o, "strengths")]
    conditions = [c for o in ops for c in (o.get("conditions") or []) if isinstance(c, str)]
    conclusive = bool(risks or strengths or conditions)

    if not conclusive:
        frame = _DD_FRAMES.get(domain)
        if domain == "risk":
            msg = ("Con la información disponible todavía no veo evidencia suficiente para señalar un "
                   "riesgo crítico. Hay, sin embargo, varios frentes que convendría validar antes de "
                   f"cerrar la tesis —especialmente {frame}—. Los trataría por ahora como puntos de due "
                   "diligence, no como riesgos confirmados.")
        elif frame:
            msg = (f"Con lo que tengo de {name} aún no puedo darte una lectura firme de "
                   f"{_DOMAIN_ES.get(domain, 'este punto')}. Para pronunciarme necesitaría revisar {frame}; "
                   "con eso sí podría cerrar la lectura.")
        else:
            msg = (f"Con la información disponible de {name} aún no puedo darte una lectura concluyente. "
                   "Dime qué ángulo te interesa y te digo exactamente qué dato falta para cerrarlo.")
        headline = msg.split(". ")[0] + "."
    else:
        # Conclusivo: prioriza lo material (riesgos/condiciones primero, luego fortalezas).
        lead_dom = _DOMAIN_ES.get(domain, "el análisis")
        bits = []
        if risks:
            bits.append("los puntos a vigilar son " + _lower_first(_join(risks[:2])))
        if strengths:
            bits.append("juega a favor " + _lower_first(_join(strengths[:2])))
        if conditions and not risks:
            bits.append("para avanzar convendría " + _lower_first(_join(conditions[:2])))
        msg = f"Sobre {lead_dom} de {name}, {'; '.join(bits)}."
        if len(ops) > 1 and out.get("answer", {}).get("conflict"):
            msg += " Las áreas no coinciden del todo; para decidir convendría convocar al comité."
        headline = f"Lectura de {lead_dom} de {name}."

    # Atribución (citar capabilities): qué área lo ha revisado. Natural, una frase.
    labels = [_area_label(t) for t in targets]
    attribution = [{"name": t, "label": _area_label(t)} for t in targets]
    if labels:
        if len(labels) == 1:
            msg += f" Esto lo ha revisado el área de {labels[0]}."
        else:
            msg += f" Lo han revisado las áreas de {_join(labels)}."
    return {"headline": headline, "message": msg, "attribution": attribution}


# ---------- L3: decisión (voz única; banda/score internos → disclosure) ----------
def _n_decision(out: Dict, ctx: Dict) -> Dict:
    name = ctx["name"]
    d = out.get("decision") or {}
    rec = d.get("recommendation")
    score = d.get("investment_score")
    conf = d.get("confidence") or 0
    phrase = _REC_PHRASE.get(rec, f"Lo revisaría con más detalle en {name}")
    conv = _conviction_phrase(score)
    lead = f"{phrase} sobre {name}" + (f", {conv}." if conv else ".")
    strengths = [_clean(t) for t in (_text(x) for x in (d.get("strengths") or [])) if t][:2]
    risks = [_clean(t) for t in (_text(x) for x in (d.get("risks") or [])) if t][:2]
    conds = [_clean(c) for c in (d.get("conditions_to_proceed") or []) if isinstance(c, str)][:2]
    body = ""
    if strengths:
        body += " A favor pesa " + _lower_first(_join(strengths)) + "."
    if risks:
        body += " Conviene vigilar " + _lower_first(_join(risks)) + "."
    elif conds:
        body += " Para avanzar habría que " + _lower_first(_join(conds)) + "."
    if conf and conf < 0.6:
        body += " Eso sí, con la información disponible mi grado de certeza es aún limitado."
    delta = ((ctx.get("entity_history") or {}).get("delta")) or {}
    evo = ""
    if delta and not delta.get("first"):
        evo = " " + _EVO_ES.get(delta.get("direction"), "")
    # Atribución: áreas que han intervenido (no abstención), sin exponer scores. Máx. 3, orden estable.
    contributors = [o.get("specialist") for o in (d.get("committee") or [])
                    if o.get("recommendation") and o.get("recommendation") != "abstain"]
    attribution = [{"name": n, "label": _area_label(n)} for n in contributors]
    attr_sentence = ""
    if contributors:
        attr_sentence = " He integrado, entre otras, las áreas de " + \
            _join([_area_label(n) for n in contributors[:3]]) + "."
    disclosure = {"band": rec, "score": score, "confidence": round(conf * 100),
                  "conviction": conviction_label(score),
                  "hint": "Puedo enseñarte cómo lo he valorado (deliberación del comité)."}
    return {"headline": lead, "message": (lead + body + evo + attr_sentence).strip(),
            "disclosure": disclosure, "attribution": attribution}


# ---------- L4: capacidades ----------
def _n_capability(out: Dict, ctx: Dict) -> Dict:
    cap = out.get("capability")
    data = (out.get("answer") or {}).get("data") or {}
    bias = ctx.get("ranking_bias") or []
    if cap == "compare":
        ranking = data.get("ranking") or []
        names = [x.get("opportunity_id") for x in ranking]
        if not names:
            ents = ctx.get("entities") or []
            if len(ents) >= 2:
                msg = (f"Para comparar {_join(ents[:3])} necesito sus datos o que las selecciones; "
                       "dímelo y las traigo.")
            else:
                msg = "Necesito al menos dos oportunidades con sus datos para poder compararlas."
            return {"headline": msg, "message": msg}
        head = f"{names[0]} encabeza la comparación" + (
            f", por delante de {_join(names[1:])}." if len(names) > 1 else ".")
        msg = "He priorizado las oportunidades por encaje: " + head
        if bias:
            msg += " He tenido en cuenta tus preferencias recientes al ordenarlas."
        return {"headline": head, "message": msg}
    if cap == "recommend":
        items = data.get("items") or []
        names = [x.get("opportunity_id") for x in items]
        if not names:
            return {"headline": "Dame un universo de oportunidades y te lo priorizo.",
                    "message": "Pásame un universo de oportunidades (con sus datos) y te devuelvo las "
                               "más encajadas para tu mandato."}
        msg = f"Para tu mandato priorizaría {_join(names[:3])}."
        if bias:
            msg += " He tenido en cuenta tus preferencias recientes al ordenarlas."
        return {"headline": msg, "message": msg}
    # portfolio u otros
    base = (out.get("answer") or {}).get("headline") or "Análisis de cartera listo."
    return {"headline": base, "message": base}


async def _maybe_ai(draft: Dict, out: Dict, ctx: Dict) -> Dict:
    """Pulido opcional por IA (solo reescribe el borrador; fact-lock). Si no hay proveedor, devuelve el
    borrador determinista. Nunca lanza."""
    provider = os.environ.get("COPILOT_VOICE_PROVIDER")
    if not provider:
        return draft
    try:
        from docstudio import model_provider as MP
        from services.copilot import persona as PERSONA
        hist = [{"user": t.get("user_text"), "copilot": t.get("summary")}
                for t in (ctx.get("history") or [])]
        context = {"draft": draft.get("message"), "verbosity": ctx.get("verbosity"),
                   "profile": ctx.get("profile"), "persona": PERSONA.system_framing(),
                   "history": hist,
                   "evidence": {"fact": out.get("fact"), "facts": out.get("facts"),
                                "opinions": out.get("opinions"), "decision": out.get("decision"),
                                "entity_history": ctx.get("entity_history")}}
        r = await MP.generate_copilot_message(context, provider=provider)
        msg = (r or {}).get("message")
        if msg and "error" not in (r or {}):
            # Guardián fact-lock: si la IA introduce una cifra que no estaba, se descarta su versión.
            allowed_text = (draft.get("message") or "") + " " + json.dumps(
                context.get("evidence") or {}, ensure_ascii=False, default=str)
            if _introduces_new_numbers(msg, allowed_text):
                return draft
            return {**draft, "headline": msg.split(". ")[0] + ".", "message": msg}
    except Exception:
        pass
    return draft


async def narrate(out: Dict, ctx: Dict) -> Dict:
    level = out.get("level")
    if level == "L0":
        draft = _n_fact(out, ctx)
    elif level in ("L1", "L2"):
        draft = _n_specialist(out, ctx)
    elif level == "L3":
        draft = _n_decision(out, ctx)
    elif level == "L4":
        draft = _n_capability(out, ctx)
    else:
        a = out.get("answer") or {}
        draft = {"headline": a.get("headline", ""), "message": a.get("detail") or a.get("headline", "")}
    return await _maybe_ai(draft, out, ctx)
