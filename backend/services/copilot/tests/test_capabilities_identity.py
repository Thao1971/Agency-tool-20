"""Manifiesto de capacidades del comité + identidad del Copilot."""

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "copilot_test")

from services.engines.investment_decision.committee import capabilities as CAP
from services.engines.investment_decision.committee import build_committee
from services.copilot import persona as P


def test_every_specialist_has_capability_and_weight():
    names = [sp.name for sp in build_committee()]
    caps = {c["name"]: c for c in CAP.all_capabilities()}
    assert set(names) == set(caps)                       # sincronía manifiesto ↔ comité
    for n in names:
        c = caps[n]
        assert c["label"] and c["scope"] and c["engines"] and "veto" in c
        assert c["weight"] is not None                   # peso en runtime, no duplicado


def test_only_legal_and_risk_have_veto():
    caps = {c["name"]: c for c in CAP.all_capabilities()}
    vetos = {n for n, c in caps.items() if c["veto"]}
    assert vetos == {"legal", "risk"}


def test_persona_is_identity_not_character():
    assert P.PERSONA["role"].lower().startswith("copiloto senior")
    assert any("inventar" in n for n in P.PERSONA["never"])
    fr = P.system_framing()
    assert "Copiloto senior de M&A" in fr and "Nunca:" in fr


if __name__ == "__main__":
    for fn in (test_every_specialist_has_capability_and_weight,
               test_only_legal_and_risk_have_veto, test_persona_is_identity_not_character):
        fn(); print("OK", fn.__name__)
