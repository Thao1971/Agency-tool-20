"""Legal — legal, gobernanza y cumplimiento. Con poder de VETO (§4). Lee la estructura de
propiedad (cap table) y señales legales. Veto EXISTENCIAL solo ante bandera legal grave
(fraude/ilegalidad); si la propiedad no es verificable ⇒ condición/pregunta, NO veto."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence

_LEGAL_FLAGS = ("fraud", "fraude", "insolven", "concurso", "litig", "sancion", "blanqueo", "ilegal")


class Legal(Specialist):
    name = "legal"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        own = ev.get("ownership") or {}
        signals = ev.get("signals") or []
        shareholders = [s for s in (own.get("shareholders") or []) if s.get("name")]
        if not own and not signals:
            return self._abstain("Sin datos legales/de propiedad; el Legal Director se abstiene.")

        evid, strengths, risks, conditions, questions = [], [], [], [], []
        veto, veto_kind = False, M.VETO_NONE
        score = 0.75

        if shareholders:
            pct = sum((s.get("pct") or 0) for s in shareholders)
            evid.append(M.evidence("master-v1", "ownership", "shareholders_pct_sum", round(pct, 1)))
            if pct >= 95:
                strengths.append(M.finding("Estructura de propiedad clara y verificable.", [evid[-1]]))
            else:
                conditions.append("Verificar la titularidad real completa (suma de participaciones < 95%).")
                questions.append(M.finding("Cadena de propiedad / titular real a completar."))
                score = 0.6
        else:
            conditions.append("Verificar el accionariado y la titularidad real (no consta en el dato).")
            score = 0.6

        # Banderas legales en señales
        legal_sig = [s for s in signals if any(f in (s.get("signal_type", "") + s.get("explanation", "")).lower()
                                               for f in _LEGAL_FLAGS)]
        for s in legal_sig[:4]:
            evid.append(M.evidence("signal-intelligence", "signal", s.get("signal_type", "legal_flag"), s.get("severity")))
            risks.append(M.finding(s.get("explanation") or s.get("signal_type") or "Bandera legal.", [evid[-1]]))
            if any(k in (s.get("signal_type", "") + s.get("explanation", "")).lower()
                   for k in ("fraud", "fraude", "blanqueo", "ilegal")):
                veto, veto_kind = True, M.VETO_EXISTENTIAL
            elif veto_kind == M.VETO_NONE:
                veto, veto_kind = True, M.VETO_BLOCKING
        if legal_sig:
            score = min(score, 0.4)

        conf = simple_confidence(len(evid) if evid else 1, 2)
        rec = M.REC_PASS if veto else (M.REC_CONDITIONS if conditions and rec_from_score(score) == M.REC_PROCEED
                                       else rec_from_score(score))
        return M.opinion(self.name, rec, round(score, 4), conf, strengths=strengths, risks=risks,
                         conditions=conditions, questions=questions, veto=veto, veto_kind=veto_kind,
                         evidence_list=evid, weight_base=S.COMMITTEE_WEIGHTS[self.name])
