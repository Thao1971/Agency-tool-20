"""Registro del comité — 10 especialistas deterministas (Fase 2 completa).

Orden estable → determinismo. Cada uno se abstiene si no tiene datos (no inventa).
Legal y Risk tienen poder de veto (§4 de la constitución)."""

from services.engines.investment_decision.committee.base import Specialist, AbstainSpecialist
from services.engines.investment_decision.committee.cfo import CFO
from services.engines.investment_decision.committee.valuation import Valuation
from services.engines.investment_decision.committee.strategy import Strategy
from services.engines.investment_decision.committee.market import Market
from services.engines.investment_decision.committee.commercial import Commercial
from services.engines.investment_decision.committee.operations import Operations
from services.engines.investment_decision.committee.hr import HR
from services.engines.investment_decision.committee.legal import Legal
from services.engines.investment_decision.committee.risk import Risk
from services.engines.investment_decision.committee.investment_director import InvestmentDirector


def build_committee():
    """Las 10 instancias del comité, en orden estable."""
    return [
        CFO(), Valuation(), Strategy(), Market(), Commercial(),
        Operations(), HR(), Legal(), Risk(), InvestmentDirector(),
    ]


COMMITTEE = build_committee()
