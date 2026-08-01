"""Autonomía proactiva: nudges gobernados por el nivel de autonomía."""

from services.copilot import proactivity as P


def _ctx(autonomy, direction=None, coverage=None):
    delta = {"first": False, "direction": direction} if direction else {}
    return {"autonomy_level": autonomy, "name": "ACME",
            "entity_history": {"delta": delta} if delta else {}, "coverage": coverage}


def test_silent_level_never_nudges():
    assert P.build({}, _ctx(0, direction="worsened")) is None


def test_worsened_informs_at_level1():
    n = P.build({}, _ctx(1, direction="worsened"))
    assert n and n["kind"] == "inform" and "perdido atractivo" in n["message"]


def test_low_coverage_informs():
    n = P.build({"level": "L3"}, _ctx(1, coverage=0.3))
    assert n and n["kind"] == "inform" and "parciales" in n["message"]


def test_improved_suggests_only_from_level2():
    assert P.build({}, _ctx(1, direction="improved")) is None       # nivel 1 no sugiere
    n = P.build({}, _ctx(2, direction="improved"))
    assert n and n["kind"] == "suggest" and "convocar al comité" in n["message"]


def test_degraded_never_nudges():
    assert P.build({"degraded": True}, _ctx(2, direction="worsened")) is None


if __name__ == "__main__":
    for fn in (test_silent_level_never_nudges, test_worsened_informs_at_level1,
               test_low_coverage_informs, test_improved_suggests_only_from_level2,
               test_degraded_never_nudges):
        fn(); print("OK", fn.__name__)
