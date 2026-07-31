"""Investment Decision Engine (investment-decision-engine-v1).

Consumer engine: se comporta como un Comité de Inversiones. Reutiliza los Intelligence
Engines existentes (Boundary First — no recrea inteligencia), puntúa de forma determinista
por especialista, construye un consenso explicable con vetos (Legal/Risk) y devuelve una
recomendación trazable. La IA solo redacta narrativa sobre evidencia bloqueada (fase posterior).

Ver memory/INVESTMENT_DECISION_ENGINE_CONSTITUTION.md y ..._DESIGN.md.
"""

ENGINE_VERSION = "investment-decision-engine-v1"
"""
El motor NO recalcula finanzas/valoración/señales; las lee de sus productores.
"""

async def analyze(request: dict) -> dict:
    """Atajo de conveniencia: `from services.engines.investment_decision import analyze`."""
    from services.engines.investment_decision.engine import analyze as _analyze
    return await _analyze(request)
