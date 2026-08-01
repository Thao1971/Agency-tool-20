"""Manifiesto de capacidades del comité — ficha DECLARATIVA por especialista.

Cada especialista ya tiene su lógica (scope, umbrales, evidencia, peso, veto) en su módulo; aquí se
declara de forma legible QUÉ cubre, QUÉ motores consume y QUÉ KPIs mira, para:
  - que el Orquestador enrute intención→especialista y EXPLIQUE ("esto lo miró el área financiera"),
  - exponerlo por API (/copilot/capabilities),
  - mantener una única fuente de verdad de las áreas del comité.
El peso se lee en runtime de scoring.COMMITTEE_WEIGHTS (no se duplica). No añade capacidad nueva:
documenta y hace enrutable/explicable la que ya existe.
"""

from typing import Dict, List
from services.engines.investment_decision import scoring as S

CAPABILITIES: Dict[str, Dict] = {
    "cfo": {
        "label": "Finanzas (CFO)",
        "scope": "Calidad del beneficio, rentabilidad, crecimiento, apalancamiento y solvencia.",
        "engines": ["financial-intelligence"],
        "kpis": ["ebitda_margin", "revenue_cagr", "net_debt_ebitda", "solvency"],
        "veto": False,
    },
    "valuation": {
        "label": "Valoración",
        "scope": "Valoración orientativa, múltiplo de referencia y rango; ajustes de EV a equity.",
        "engines": ["valuation", "financial-intelligence"],
        "kpis": ["enterprise_value", "ev_ebitda", "valuation_range", "margin_percentile"],
        "veto": False,
    },
    "strategy": {
        "label": "Estrategia y encaje",
        "scope": "Encaje estratégico con el mandato del comprador, tesis y sinergias.",
        "engines": ["recommendation", "strategy"],
        "kpis": ["strategic_fit", "synergies"],
        "veto": False,
    },
    "market": {
        "label": "Mercado y competencia",
        "scope": "Posición competitiva, estructura y consolidación del sector.",
        "engines": ["sector-intelligence", "fragmentation-e7"],
        "kpis": ["hhi", "standalone_targets_count", "market_position"],
        "veto": False,
    },
    "commercial": {
        "label": "Comercial",
        "scope": "Cartera de clientes, recurrencia de ingresos y concentración comercial.",
        "engines": ["financial-intelligence"],
        "kpis": ["revenue_per_employee", "client_concentration", "recurrence"],
        "veto": False,
    },
    "operations": {
        "label": "Operaciones",
        "scope": "Escalabilidad, eficiencia y dependencia de personas clave.",
        "engines": ["financial-intelligence"],
        "kpis": ["revenue_per_employee", "employees", "scalability"],
        "veto": False,
    },
    "hr": {
        "label": "Equipo y sucesión",
        "scope": "Continuidad del equipo directivo y plan de sucesión.",
        "engines": ["succession-intelligence-e2"],
        "kpis": ["succession_risk", "management_continuity"],
        "veto": False,
    },
    "legal": {
        "label": "Legal y societario",
        "scope": "Estructura de propiedad y control, contingencias y contratos críticos.",
        "engines": ["ownership", "control-graph-t3"],
        "kpis": ["ownership_structure", "control_chain", "contingencies"],
        "veto": True,
    },
    "risk": {
        "label": "Riesgo",
        "scope": "Riesgo agregado (regulatorio, operativo, financiero, de ejecución).",
        "engines": ["signal-intelligence", "financial-intelligence"],
        "kpis": ["risk_flags", "downside"],
        "veto": True,
    },
    "investment_director": {
        "label": "Dirección de inversiones",
        "scope": "Síntesis del comité, coherencia del caso y recomendación final.",
        "engines": ["investment-decision-engine-v1"],
        "kpis": ["consensus", "dispersion", "confidence"],
        "veto": False,
    },
}


def capability(name: str) -> Dict:
    base = dict(CAPABILITIES.get(name, {}))
    base["name"] = name
    base["weight"] = S.COMMITTEE_WEIGHTS.get(name)     # peso en runtime (no se duplica)
    return base


def all_capabilities() -> List[Dict]:
    from services.engines.investment_decision.committee import build_committee
    return [capability(sp.name) for sp in build_committee()]
