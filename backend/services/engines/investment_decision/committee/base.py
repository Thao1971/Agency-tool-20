"""Base del comité — cada especialista es un scorer DETERMINISTA que consume la evidencia
y emite un `SpecialistOpinion`. Nunca texto libre; nunca inventa (si no hay datos → abstain)."""

from typing import Dict, List
from services.engines.investment_decision import models as M
from services.engines.investment_decision import scoring as S


def rec_from_score(score: float) -> str:
    if score >= 0.70:
        return M.REC_PROCEED
    if score >= 0.55:
        return M.REC_CONDITIONS
    if score >= 0.45:
        return M.REC_EXPLORE
    return M.REC_PASS


def simple_confidence(n_present: int, n_expected: int) -> Dict:
    cov = (n_present / n_expected) if n_expected else 0.0
    return S.confidence(coverage=cov, data_quality=cov, cross_engine_consistency=cov,
                        recency=cov, committee_agreement=1.0)


class Specialist:
    """Contrato: name (clave en COMMITTEE_WEIGHTS) + evaluate()."""
    name: str = "base"

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:  # -> SpecialistOpinion
        raise NotImplementedError

    def _abstain(self, reason: str, questions: List[str] = None) -> Dict:
        return M.opinion(self.name, M.REC_ABSTAIN, None,
                         S.confidence(0, 0, 0, 0, 1.0),
                         questions=[M.finding(q) for q in (questions or [reason])],
                         weight_base=S.COMMITTEE_WEIGHTS.get(self.name, 0.0))


class AbstainSpecialist(Specialist):
    """Especialista aún no implementado (Fase 2). Se registra para que el comité sea completo,
    pero se abstiene con una pregunta abierta — no arrastra el score ni inventa."""
    def __init__(self, name: str, note: str):
        self.name = name
        self._note = note

    def evaluate(self, ev: Dict, profile: Dict) -> Dict:
        return self._abstain(self._note)
