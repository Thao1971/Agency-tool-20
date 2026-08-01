"""ARROBA Copilot — Next Best Action + mini-cards (copilot-voice-v1).

Tras responder, el Copilot ofrece el siguiente movimiento natural: una mini-card de la entidad y hasta
~3 acciones sugeridas (chips). El backend emite la INTENCIÓN (p. ej. navigate → /company/{id}); ARROBA
resuelve el deep-link. Propone, no dispone: por defecto (autonomía 1·Informa) solo sugiere; auto-navegar
requiere autonomía alta (estado CIM E) y nada con efecto externo se ejecuta sin autorización.
Fact-lock: la card solo usa datos ya disponibles. Ver ARROBA_COPILOT_VOICE_NATURAL_EXECUTIVE.md.
"""

from typing import Dict, List, Optional

ACTIONS_VERSION = "copilot-actions-v1"
_MAX_ACTIONS = 3

# Contrato con el front de ARROBA: tipos de acción, qué params llevan y qué debe hacer la UI.
# El backend emite la INTENCIÓN; ARROBA resuelve el deep-link/efecto. `external_effect=True` ⇒ la UI
# debe pedir confirmación y (si aplica) autorización antes de ejecutar.
CONTRACT = {
    "version": ACTIONS_VERSION,
    "kinds": {
        "navigate": {"params": ["target", "company_id?"], "ui": "Navegar al deep-link `target`.",
                     "external_effect": False},
        "analyze": {"params": ["company_id"], "ui": "Lanzar análisis del comité (L3) sobre la compañía.",
                    "external_effect": False},
        "open_deliberation": {"params": ["decision_id"],
                              "ui": "Abrir el panel de deliberación de esa decisión.",
                              "external_effect": False},
        "generate_document": {"params": ["doc_type", "company_id"],
                              "ui": "Abrir el generador de documento (teaser/one-pager/memo) precargado.",
                              "external_effect": False},
        "add_to_watchlist": {"params": ["company_id?", "query?"],
                             "ui": "Añadir la compañía a la watchlist del usuario.",
                             "external_effect": False},
        "explain_order": {"params": [], "ui": "Mostrar '¿por qué este orden?' (sesgo de ranking).",
                          "external_effect": False},
        "search": {"params": ["query"], "ui": "Abrir búsqueda con la query.", "external_effect": False},
    },
    "routes": {"company_profile": "/company/{company_id}", "compare": "/compare",
               "document_new": "/documents/new"},
    "note": ("El Copilot propone; la UI dispone. Ninguna acción se auto-ejecuta salvo autonomía alta "
             "(estado CIM E) y, para external_effect=True, siempre con autorización explícita."),
}


def _act(id_: str, label: str, kind: str, target: Optional[str] = None,
         params: Optional[Dict] = None, requires_confirmation: bool = False) -> Dict:
    return {"id": id_, "label": label, "kind": kind, "target": target,
            "params": params or {}, "requires_confirmation": requires_confirmation}


def _entity_card(out: Dict, ctx: Dict) -> Optional[Dict]:
    if not ctx.get("resolved"):
        return None
    name, cid = ctx.get("name"), ctx.get("entity_id")
    kpis = out.get("facts") or []
    if not kpis and (out.get("fact") or {}).get("available"):
        f = out["fact"]
        kpis = [{"label": f.get("label"), "value": f.get("value")}]
    card = {"type": "entity", "name": name, "company_id": cid, "kpis": kpis[:4]}
    disc = (out.get("answer") or {}).get("disclosure")
    if disc:
        card["conviction"] = disc.get("conviction")   # chip cualitativo (no el número crudo)
    return card


def build(out: Dict, ctx: Dict) -> Dict:
    """Devuelve {'card': <mini-card|None>, 'actions': [<=3]}. Determinista."""
    level = out.get("level")
    name = ctx.get("name") or "la compañía"
    cid = ctx.get("entity_id")
    resolved = bool(ctx.get("resolved"))
    actions: List[Dict] = []

    if level == "L4":
        actions.append(_act("open_compare", "Abrir comparador", "navigate", "/compare"))
        if ctx.get("bias"):
            actions.append(_act("explain_order", "¿Por qué este orden?", "explain_order"))
        return {"card": None, "actions": actions[:_MAX_ACTIONS]}

    if not resolved:
        # Empresa no encontrada en el sistema → buscar / añadir, no "ver ficha".
        actions.append(_act("search", f"Buscar {name}", "search", params={"query": name}))
        actions.append(_act("add_watchlist", f"Añadir {name} a seguimiento", "add_to_watchlist",
                            params={"query": name}))
        return {"card": None, "actions": actions[:_MAX_ACTIONS]}

    card = _entity_card(out, ctx)

    if level in ("L0", "L1", "L2"):
        actions.append(_act("open_company", f"Ver ficha de {name}", "navigate",
                            f"/company/{cid}", {"company_id": cid}))
        if level == "L0":
            actions.append(_act("full_analysis", "Análisis completo", "analyze",
                                params={"company_id": cid}))
        elif out.get("answer", {}).get("conflict"):
            actions.append(_act("convene_committee", "Convocar al comité", "analyze",
                                params={"company_id": cid}))
    elif level == "L3":
        did = (out.get("decision") or {}).get("decision_id")
        actions.append(_act("open_deliberation", "Ver deliberación", "open_deliberation",
                            params={"decision_id": did}))
        actions.append(_act("gen_teaser", "Generar teaser", "generate_document",
                            "/documents/new", {"doc_type": "teaser", "company_id": cid}))
        actions.append(_act("add_watchlist", "Añadir a seguimiento", "add_to_watchlist",
                            params={"company_id": cid}))

    return {"card": card, "actions": actions[:_MAX_ACTIONS]}
