"""Investment Director — lectura global preliminar y encaje con el mandato del comprador.
Independiente de los demás especialistas (evita circularidad): valora calidad del negocio
(crecimiento+margen), solidez de la tesis (fortalezas del assessment) y encaje con el mandato
(sector/tamaño si se aporta)."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence


class InvestmentDirector(Specialist):
    name = "investment_director"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        kp = ev.get("kpis") or {}
        ident = ev.get("identity") or {}
        assess = ev.get("assessment") or {}
        margin, cagr = kp.get("ebitda_margin"), kp.get("revenue_cagr")
        strengths_n = len(assess.get("strengths") or [])
        if margin is None and cagr is None and not strengths_n:
            return self._abstain("Sin base para la lectura global (Investment Director).")

        subs, evid, strengths = [], [], []
        if margin is not None:
            subs.append(1.0 if margin >= 0.15 else 0.7 if margin >= 0.08 else 0.4)
            evid.append(M.evidence("financial-intelligence", "financial", "ebitda_margin", round(margin, 4)))
        if cagr is not None:
            subs.append(1.0 if cagr >= 0.10 else 0.7 if cagr >= 0.03 else 0.4)
            evid.append(M.evidence("financial-intelligence", "financial", "revenue_cagr", round(cagr, 4)))
        if strengths_n:
            subs.append(S.clamp(0.5 + 0.1 * strengths_n))
            evid.append(M.evidence("financial-intelligence", "assessment", "strengths_count", strengths_n))
            for s in (assess.get("strengths") or [])[:2]:
                strengths.append(M.finding(s))

        # Encaje con el mandato (si se aporta sector/tamaño objetivo)
        mandate = (profile or {}).get("mandate") or {}
        questions = []
        if mandate.get("sector"):
            match = str(mandate["sector"]).lower() in str(ident.get("cnae_description", "")).lower()
            subs.append(0.9 if match else 0.5)
            evid.append(M.evidence("buyer-mandate", "mandate", "sector_match", match))
        else:
            questions.append(M.finding("Encaje con el mandato: definir sector/tamaño objetivo del comprador."))

        score = S.clamp(sum(subs) / len(subs)) if subs else 0.5
        conf = simple_confidence(len(subs), 3)
        return M.opinion(self.name, rec_from_score(score), score, conf, strengths=strengths,
                         questions=questions, evidence_list=evid, weight_base=S.COMMITTEE_WEIGHTS[self.name])
