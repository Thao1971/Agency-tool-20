"""Valuation — precio y retorno. Lee el motor de valoración (bundle.valuation) y comparables.
No recalcula: interpreta método/base del múltiplo y el rango, y valora si el precio es razonable."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence

_VAL = "valuation-intelligence"


class Valuation(Specialist):
    name = "valuation"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        val = ev.get("valuation") or {}
        method = val.get("method")
        if not method or method == "insufficient_data":
            return self._abstain("Sin valoración disponible del motor; el Valuation Director se abstiene.")

        basis = val.get("multiple_basis", "")
        evx = val.get("enterprise_value") or val.get("equity_value") or val.get("ev")
        rng = val.get("range") or {}
        evid, strengths, conditions, weaknesses = [], [], [], []

        # Base del múltiplo: observado de mercado > referencia inferida
        if basis == "market_observed":
            base_score = 0.8
            strengths.append(M.finding("Valoración apoyada en múltiplo de mercado observado (M&A Radar)."))
        else:
            base_score = 0.6
            conditions.append("Contrastar el múltiplo de referencia inferido con transacciones comparables reales.")
        if evx:
            evid.append(M.evidence(_VAL, "valuation", "enterprise_value", round(float(evx), 0)))
        if rng.get("low") and rng.get("high"):
            evid.append(M.evidence(_VAL, "valuation", "ev_range", [rng["low"], rng["high"]]))

        # El perfil PE es más exigente con el precio; el estratégico lo tolera si hay encaje
        pt = (profile or {}).get("type", "strategic")
        if pt == "private_equity":
            base_score -= 0.05
            conditions.append("Verificar que el retorno (MOIC/TIR) cumple el umbral del fondo al precio propuesto.")
        elif pt in ("strategic", "corporate_venture"):
            base_score += 0.03

        score = S.clamp(base_score)
        conf = simple_confidence(1 + (1 if evx else 0) + (1 if rng else 0), 3)
        rec = M.REC_CONDITIONS if (conditions and rec_from_score(score) == M.REC_PROCEED) else rec_from_score(score)
        return M.opinion(self.name, rec, score, conf, strengths=strengths, weaknesses=weaknesses,
                         conditions=conditions, evidence_list=evid,
                         weight_base=S.COMMITTEE_WEIGHTS[self.name])
