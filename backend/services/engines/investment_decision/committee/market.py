"""Market — atractivo del mercado y posición competitiva. Lee fragmentación (HHI, actores),
comparables (percentil de la empresa) y, si existe, sector/economic intelligence."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence


class Market(Specialist):
    name = "market"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        frag = ev.get("fragmentation") or {}
        comp = ev.get("comparables") or {}
        sector = ev.get("sector_intelligence") or {}
        pct = comp.get("subject_ebitda_margin_percentile")
        hhi = frag.get("hhi")
        if hhi is None and pct is None and not sector:
            return self._abstain("Sin datos de mercado suficientes (HHI/percentiles).")

        subs, evid, strengths, weaknesses = [], [], [], []
        # Estructura del mercado: fragmentado (HHI bajo) = oportunidad de consolidación
        if hhi is not None:
            sh = 0.85 if hhi < 1500 else 0.65 if hhi < 2500 else 0.45
            subs.append(sh)
            evid.append(M.evidence("fragmentation-v1", "investment", "hhi", round(hhi, 0)))
            (strengths if hhi < 1500 else weaknesses).append(
                M.finding(f"HHI {hhi:.0f}: mercado {'fragmentado (consolidable)' if hhi<1500 else 'concentrado'}.", [evid[-1]]))
        # Posición competitiva de la empresa (percentil de margen)
        if pct is not None:
            subs.append(S.clamp(pct))
            evid.append(M.evidence("financial-intelligence", "comparables", "ebitda_margin_percentile", round(pct, 4)))
            strengths.append(M.finding(f"Margen por encima del {pct*100:.0f}% del sector.", [evid[-1]]))

        score = S.clamp(sum(subs) / len(subs)) if subs else 0.5
        conf = simple_confidence(len(subs), 2)
        return M.opinion(self.name, rec_from_score(score), score, conf, strengths=strengths,
                         weaknesses=weaknesses, evidence_list=evid,
                         weight_base=S.COMMITTEE_WEIGHTS[self.name])
