"""Operations — escalabilidad y productividad. Lee ingresos/empleado y ciclo de caja (ratios),
más la tendencia de margen (apalancamiento operativo)."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence


class Operations(Specialist):
    name = "operations"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        kp = ev.get("kpis") or {}
        ratios = ev.get("financials", {}) if isinstance(ev.get("financials"), dict) else {}
        rpe = kp.get("revenue_per_employee")
        ccc = ((ev.get("ratios") or {}).get("cash_conversion_cycle") or {}).get("value") \
            if isinstance(ev.get("ratios"), dict) else None
        eg = kp.get("ebitda_growth_yoy")
        if rpe is None and ccc is None and eg is None:
            return self._abstain("Sin datos operativos (productividad/circulante).")

        subs, evid, strengths = [], [], []
        if rpe:
            sp = 1.0 if rpe >= 250_000 else 0.7 if rpe >= 120_000 else 0.45
            subs.append(sp); evid.append(M.evidence("financial-intelligence", "financial", "revenue_per_employee", round(rpe, 0)))
            if rpe >= 120_000:
                strengths.append(M.finding(f"Productividad de {rpe:,.0f} € por empleado.", [evid[-1]]))
        if ccc is not None:
            sc = 1.0 if ccc <= 30 else 0.7 if ccc <= 60 else 0.45
            subs.append(sc); evid.append(M.evidence("financial-intelligence", "financial", "cash_conversion_cycle", round(ccc, 0)))
        if eg is not None:
            subs.append(1.0 if eg > 0 else 0.4)
            evid.append(M.evidence("financial-intelligence", "financial", "ebitda_growth_yoy", round(eg, 4)))

        score = S.clamp(sum(subs) / len(subs)) if subs else 0.5
        conf = simple_confidence(len(subs), 3)
        return M.opinion(self.name, rec_from_score(score), score, conf, strengths=strengths,
                         evidence_list=evid, weight_base=S.COMMITTEE_WEIGHTS[self.name])
