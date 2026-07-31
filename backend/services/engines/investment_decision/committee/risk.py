"""Risk — riesgo agregado. Con poder de VETO (§4 de la constitución). Lee señales de riesgo,
solvencia y apalancamiento. Veto EXISTENCIAL (insolvencia/fraude) → REJECT; veto BLOQUEANTE
(riesgo alto no mitigado) → techo en PROCEED_WITH_CONDITIONS."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence

_SIG = "signal-intelligence"
_FIN = "financial-intelligence"


class Risk(Specialist):
    name = "risk"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        kp = ev.get("kpis") or {}
        signals = ev.get("signals") or []
        evo = ev.get("evolution") or {}
        pts = sorted([p for p in (evo.get("points") or []) if p.get("year")], key=lambda x: x["year"])
        last = pts[-1] if pts else {}
        solvency = kp.get("solvency")
        ebitda = kp.get("ebitda") or last.get("ebitda")
        nfp = last.get("net_financial_position")

        if solvency is None and not signals and nfp is None:
            return self._abstain("Sin datos de riesgo suficientes; el Risk Director se abstiene.")

        risks, conditions, evid = [], [], []
        veto, veto_kind = False, M.VETO_NONE
        penalty = 0.0

        risk_signals = [s for s in signals if s.get("severity") == "risk"]
        for s in risk_signals[:6]:
            evid.append(M.evidence(_SIG, "signal", s.get("signal_type", "risk"), s.get("severity")))
            risks.append(M.finding(s.get("explanation") or s.get("signal_type") or "Señal de riesgo.", [evid[-1]]))
        penalty += min(0.4, 0.1 * len(risk_signals))

        # Veto existencial: insolvencia (autonomía financiera negativa/ínfima)
        if solvency is not None:
            evid.append(M.evidence(_FIN, "financial", "solvency", round(float(solvency), 4)))
            if solvency <= 0:
                veto, veto_kind = True, M.VETO_EXISTENTIAL
                risks.append(M.finding("Patrimonio neto negativo: riesgo de insolvencia.", [evid[-1]]))
            elif solvency < 0.10:
                penalty += 0.3
                conditions.append("Reforzar el balance / reestructurar deuda antes de cerrar (autonomía financiera < 10%).")

        # Veto bloqueante: apalancamiento extremo
        if nfp is not None and ebitda:
            lev = nfp / ebitda
            evid.append(M.evidence(_FIN, "financial", "net_debt_ebitda", round(lev, 2)))
            if lev >= 5:
                veto, veto_kind = (True, M.VETO_BLOCKING) if veto_kind != M.VETO_EXISTENTIAL else (veto, veto_kind)
                conditions.append("Apalancamiento crítico (≥5x): condicionar la operación a desapalancamiento.")

        score = S.clamp(1.0 - penalty)
        conf = simple_confidence(len(evid), 3)
        rec = M.REC_PASS if veto else (M.REC_CONDITIONS if conditions and rec_from_score(score) == M.REC_PROCEED
                                       else rec_from_score(score))
        return M.opinion(self.name, rec, score, conf, risks=risks, conditions=conditions,
                         veto=veto, veto_kind=veto_kind, evidence_list=evid,
                         weight_base=S.COMMITTEE_WEIGHTS[self.name])
