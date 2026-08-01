"""ARROBA Copilot — capa de orquestación (copilot-orchestrator-v1).

Pieza INVISIBLE entre la voz (ARROBA Copilot) y los especialistas/comité. Clasifica la intención,
enruta al mínimo aparato necesario (L0 hecho · L1 especialista · L2 panel · L3 comité · L4 capacidad),
fusiona y devuelve UN resultado para que la voz lo redacte. No habla, no calcula, no decide por su
cuenta. Ver memory/ARROBA_COPILOT_ORCHESTRATOR.md.
"""

ORCHESTRATOR_VERSION = "copilot-orchestrator-v1"


async def orchestrate(request: dict) -> dict:
    from services.copilot.orchestrator import orchestrate as _o
    return await _o(request)
