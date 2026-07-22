"""Canonical recommended-action catalog (D4). Versioned enum. NO free text.

Consumers (arroba, Copilot, …) decide how to present these structured actions.
"""

ACTIONS_VERSION = "act-v1"

# The closed, canonical set. Extending = add here + bump ACTIONS_VERSION (additive, compatible).
CANONICAL_ACTIONS = [
    "analyze", "monitor", "value", "compare", "investigate", "contact",
    "buy", "sell", "raise_capital", "add_to_watchlist",
    "request_due_diligence", "consult_advisor",
]

_ACTION_SET = set(CANONICAL_ACTIONS)


def validate(actions):
    """Drop any action not in the canonical enum (engine never emits free text)."""
    return [a for a in (actions or []) if a in _ACTION_SET]
