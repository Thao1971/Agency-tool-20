"""HR — equipo y continuidad. Lee señales de sucesión/relevo (Signal Engine) y la plantilla.
La sucesión es dual: catalizador de venta PERO riesgo de continuidad del equipo clave."""

from typing import Dict
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S
from services.engines.investment_decision.committee.base import Specialist, rec_from_score, simple_confidence


class HR(Specialist):
    name = "hr"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        signals = ev.get("signals") or []
        ident = ev.get("identity") or {}
        wf = ident.get("workforce") or {}
        plantilla = wf.get("total")
        succ = [s for s in signals if "suces" in (s.get("signal_type", "").lower())
                or s.get("severity") == "succession" or "relevo" in (s.get("explanation", "").lower())]
        if not signals and plantilla is None:
            return self._abstain("Sin datos de equipo/continuidad; el HR Director se abstiene.")

        evid, strengths, risks, questions = [], [], [], []
        score = 0.6
        if succ:
            evid.append(M.evidence("signal-intelligence", "signal", "succession", True))
            strengths.append(M.finding("Señal de relevo/sucesión: coherente con una venta ordenada.", [evid[-1]]))
            risks.append(M.finding("Continuidad del equipo directivo tras la operación a asegurar.", [evid[-1]]))
            questions.append(M.finding("Plan de retención e incentivos del management post-cierre."))
            score = 0.55
        if plantilla:
            evid.append(M.evidence("master-v1", "workforce", "plantilla", int(plantilla)))
        questions.append(M.finding("Dependencia de personas clave y profundidad del organigrama: confirmar en DD."))

        conf = simple_confidence(len(evid) if evid else 1, 2)
        return M.opinion(self.name, rec_from_score(score), round(score, 4), conf, strengths=strengths,
                         risks=risks, questions=questions, evidence_list=evid,
                         weight_base=S.COMMITTEE_WEIGHTS[self.name])
