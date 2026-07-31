"""Commercial — clientes, recurrencia e ingresos. Los datos de cartera (concentración, churn)
rara vez están en el dato estructurado ⇒ el especialista es honesto: usa la tracción de ingresos
como PROXY (dato real) y SIEMPRE deja abierta la pregunta de concentración; si hay datos de
clientes en Document Intelligence, los usa."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence


class Commercial(Specialist):
    name = "commercial"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        kp = ev.get("kpis") or {}
        docs = ev.get("documents") or {}
        clients = docs.get("clients") or docs.get("customers")
        cagr, yoy = kp.get("revenue_cagr"), kp.get("revenue_growth_yoy")
        if cagr is None and yoy is None and not clients:
            return self._abstain("Sin datos comerciales; el Commercial Director se abstiene.")

        evid, strengths, questions = [], [], []
        growth = cagr if cagr is not None else yoy
        score = 0.5
        if growth is not None:
            score = 1.0 if growth >= 0.10 else 0.7 if growth >= 0.03 else 0.45 if growth >= 0 else 0.25
            evid.append(M.evidence("financial-intelligence", "financial", "revenue_growth(proxy)", round(growth, 4)))
            strengths.append(M.finding(f"Tracción de ingresos {growth*100:+.1f}% (proxy comercial).", [evid[-1]]))
        if clients:
            evid.append(M.evidence("document-intelligence", "documents", "clients", True))
        questions.append(M.finding("Concentración de clientes (top-5/top-10), recurrencia y churn: a confirmar en DD."))

        conf = simple_confidence(len(evid), 2)
        return M.opinion(self.name, rec_from_score(score), round(score, 4), conf, strengths=strengths,
                         questions=questions, evidence_list=evid, weight_base=S.COMMITTEE_WEIGHTS[self.name])
