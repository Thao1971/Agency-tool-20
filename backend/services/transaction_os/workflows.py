"""Versioned Workflow Templates (DTX2) + declarative State Machine (DTX3).

Templates evolve without breaking in-flight transactions (each Transaction pins its
workflow_version + state_machine_version). No implicit transitions.
"""

STATE_MACHINE_VERSION = "state-machine-v1"

# v1 scope (DTX10): Origination → Due Diligence (initial). Later stages declared but deferred.
STAGES_V1 = ["origination", "qualification", "screening", "outreach",
             "nda", "data_room", "valuation", "due_diligence_initial"]
STAGES_DEFERRED = ["ioi", "loi", "negotiation", "spa", "signing", "closing", "post_closing"]

WORKFLOW_TEMPLATES = {
    "buy_side_v1": {"version": "buy_side_v1", "side": "buy", "stages": list(STAGES_V1)},
    "sell_side_v1": {"version": "sell_side_v1", "side": "sell", "stages": list(STAGES_V1)},
    "capital_raise_v1": {"version": "capital_raise_v1", "side": "capital", "stages": list(STAGES_V1)},
    "partnership_v1": {"version": "partnership_v1", "side": "partnership", "stages": list(STAGES_V1)},
}

# Global transaction states
GLOBAL_STATES = ["draft", "sourcing", "engaged", "diligence",
                 "closed_won", "closed_lost", "abandoned", "on_hold"]
TERMINAL_STATES = ["closed_won", "closed_lost", "abandoned"]

# High-risk actions requiring explicit human Approval (DTX5)
HIGH_RISK_ACTIONS = ["send_nda", "open_data_room", "share_sensitive_info",
                     "send_ioi", "send_loi", "accept_terms", "advance_to_due_diligence",
                     "sign_spa", "close_deal"]

# Declarative transitions: from → to with event, guards, authorized roles, effects.
TRANSITIONS = [
    {"from": "draft", "to": "sourcing", "event": "thesis_instantiated",
     "guards": ["has_thesis"], "authorized": ["advisor", "platform"], "effects": ["activate_origination"]},
    {"from": "sourcing", "to": "engaged", "event": "buyer_contacted",
     "guards": ["screening_complete"], "authorized": ["advisor", "buyer", "seller"],
     "effects": ["open_outreach"]},
    {"from": "engaged", "to": "diligence", "event": "advance_to_due_diligence",
     "guards": ["nda_signed", "data_room_open", "approval:advance_to_due_diligence"],
     "authorized": ["advisor", "buyer"], "effects": ["start_dd"]},
    {"from": "diligence", "to": "closed_won", "event": "deal_closed",
     "guards": ["approval:close_deal"], "authorized": ["advisor", "buyer", "seller"],
     "effects": ["finalize"]},
    {"from": "*", "to": "closed_lost", "event": "deal_lost",
     "guards": [], "authorized": ["advisor", "buyer", "seller", "platform"], "effects": ["finalize"]},
    {"from": "*", "to": "abandoned", "event": "abandon",
     "guards": [], "authorized": ["advisor", "platform"], "effects": ["finalize"]},
    {"from": "*", "to": "on_hold", "event": "hold",
     "guards": [], "authorized": ["advisor", "platform"], "effects": []},
]

# Reusable domain events (DTX8) that feed the Intelligence Layer
DOMAIN_EVENTS = ["buyer_contacted", "nda_signed", "offer_received", "loi_sent",
                 "dd_started", "deal_lost", "deal_closed"]


def template(name: str):
    return WORKFLOW_TEMPLATES.get(name)


def find_transition(from_state: str, event: str):
    for t in TRANSITIONS:
        if t["event"] == event and (t["from"] == from_state or t["from"] == "*"):
            return t
    return None
