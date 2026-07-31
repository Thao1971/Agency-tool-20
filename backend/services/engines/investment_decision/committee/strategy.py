"""Strategy — encaje estratégico y calidad de plataforma. Lee kpis (calidad del negocio),
assessment (fortalezas), fragmentación (oportunidad de consolidación) y el perfil de comprador."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence


class Strategy(Specialist):
    name = "strategy"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        kp = ev.get("kpis") or {}
        assess = ev.get("assessment") or {}
        frag = ev.get("fragmentation") or {}
        margin, cagr = kp.get("ebitda_margin"), kp.get("revenue_cagr")
        if margin is None and cagr is None and not assess.get("strengths"):
            return self._abstain("Sin base para evaluar el encaje estratégico (Fase 2).")

        subs, evid, strengths = [], [], []
        # Calidad de plataforma (rentabilidad + crecimiento)
        if margin is not None:
            sm = 1.0 if margin >= 0.15 else 0.7 if margin >= 0.08 else 0.4
            subs.append(sm); evid.append(M.evidence("strategy-intelligence", "strategy", "ebitda_margin", round(margin, 4)))
        if cagr is not None:
            sg = 1.0 if cagr >= 0.10 else 0.7 if cagr >= 0.03 else 0.4
            subs.append(sg); evid.append(M.evidence("strategy-intelligence", "strategy", "revenue_cagr", round(cagr, 4)))
            if cagr >= 0.05:
                strengths.append(M.finding("Plataforma con crecimiento para construir sobre ella.", [evid[-1]]))
        # Oportunidad de consolidación (mercado fragmentado = buy & build)
        st = frag.get("standalone_targets_count")
        if st:
            subs.append(0.85); evid.append(M.evidence("fragmentation-v1", "investment", "standalone_targets", st))
            strengths.append(M.finding(f"{st} objetivos independientes: recorrido de buy & build.", [evid[-1]]))
        for s in (assess.get("strengths") or [])[:2]:
            strengths.append(M.finding(s))

        # Modulador de perfil: estratégico/holding valoran más el encaje
        pt = (profile or {}).get("type", "strategic")
        base = sum(subs) / len(subs) if subs else 0.5
        if pt in ("strategic", "holding", "corporate_venture"):
            base = S.clamp(base + 0.05)
        score = S.clamp(base)
        conf = simple_confidence(len(subs), 3)
        return M.opinion(self.name, rec_from_score(score), score, conf, strengths=strengths,
                         evidence_list=evid, weight_base=S.COMMITTEE_WEIGHTS[self.name])
