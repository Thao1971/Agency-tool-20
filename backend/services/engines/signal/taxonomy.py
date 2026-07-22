"""Canonical, versioned Signal Taxonomy (D6).

Closed set of 9 categories. Signal types live ONLY here. Adding a new source (BORME,
CNMV, PLACSP, grants, M&A) means adding new types under these categories — never
breaking the contract. Thresholds are NOT here (D1: resolved by context in thresholds.py).
UI concepts are NEVER here (D8).
"""

TAXONOMY_VERSION = "tax-v1"

# 9 canonical categories
CATEGORIES = [
    "financial", "growth", "risk", "ownership",
    "corporate", "market", "opportunity", "transaction", "operational",
]

# polarity: how an increase in `impact` should read for trend (D5).
#   negative → higher impact = worsening · positive → higher impact = improving
# severity: legible label DERIVED from dimensions (D8: structured, not UI)
# pending: declared in taxonomy but its source is not yet ingested → never emitted
# Each type: category, polarity, severity, base_impact, base_urgency, actions, dependencies, description
SIGNAL_TYPES = {
    # ── financial ──
    "financial.margin_strong": dict(category="financial", polarity="positive", severity="positive",
        base_impact=0.6, base_urgency=0.3, actions=["analyze", "value", "add_to_watchlist"],
        dependencies=["financial-intelligence-v1"], description="EBITDA margin above sector-strong threshold."),
    "financial.margin_weak": dict(category="financial", polarity="negative", severity="warning",
        base_impact=0.5, base_urgency=0.5, actions=["analyze", "investigate"],
        dependencies=["financial-intelligence-v1"], description="EBITDA margin below weak threshold."),
    "financial.low_liquidity": dict(category="financial", polarity="negative", severity="risk",
        base_impact=0.6, base_urgency=0.8, actions=["investigate", "monitor", "request_due_diligence"],
        dependencies=["financial-intelligence-v1"], description="Current ratio below 1.0."),
    "financial.high_leverage": dict(category="financial", polarity="negative", severity="risk",
        base_impact=0.6, base_urgency=0.6, actions=["investigate", "monitor"],
        dependencies=["financial-intelligence-v1"], description="Debt/equity above leverage threshold."),
    "financial.negative_equity": dict(category="financial", polarity="negative", severity="critical",
        base_impact=0.9, base_urgency=0.9, actions=["investigate", "request_due_diligence", "consult_advisor"],
        dependencies=["financial-intelligence-v1"], description="Negative equity (technical insolvency risk)."),
    "financial.net_loss": dict(category="financial", polarity="negative", severity="risk",
        base_impact=0.6, base_urgency=0.6, actions=["analyze", "investigate"],
        dependencies=["financial-intelligence-v1"], description="Negative net income in latest year."),
    "financial.quality_low": dict(category="financial", polarity="negative", severity="warning",
        base_impact=0.4, base_urgency=0.4, actions=["investigate", "request_due_diligence"],
        dependencies=["financial-intelligence-v1"], description="Financial quality score below threshold."),

    # ── growth ──
    "growth.revenue_surge": dict(category="growth", polarity="positive", severity="opportunity",
        base_impact=0.7, base_urgency=0.5, actions=["analyze", "contact", "add_to_watchlist"],
        dependencies=["financial-intelligence-v1"], description="Revenue YoY growth above surge threshold."),
    "growth.ebitda_expansion": dict(category="growth", polarity="positive", severity="positive",
        base_impact=0.6, base_urgency=0.4, actions=["analyze", "add_to_watchlist"],
        dependencies=["financial-intelligence-v1"], description="EBITDA YoY growth above threshold."),
    "growth.sustained": dict(category="growth", polarity="positive", severity="opportunity",
        base_impact=0.75, base_urgency=0.4, actions=["analyze", "contact", "add_to_watchlist"],
        dependencies=["financial-intelligence-v1"], description="Multi-year revenue CAGR above threshold."),

    # ── risk ──
    "risk.revenue_decline": dict(category="risk", polarity="negative", severity="risk",
        base_impact=0.6, base_urgency=0.6, actions=["investigate", "monitor"],
        dependencies=["financial-intelligence-v1"], description="Revenue YoY decline beyond threshold."),
    "risk.sustained_decline": dict(category="risk", polarity="negative", severity="risk",
        base_impact=0.7, base_urgency=0.7, actions=["investigate", "monitor", "request_due_diligence"],
        dependencies=["financial-intelligence-v1"], description="Revenue declines across ≥2 consecutive years."),
    "risk.revenue_anomaly": dict(category="risk", polarity="negative", severity="warning",
        base_impact=0.5, base_urgency=0.5, actions=["investigate"],
        dependencies=["financial-intelligence-v1"], description="Abnormal revenue jump/drop (>50%)."),
    "risk.balance_inconsistency": dict(category="risk", polarity="negative", severity="warning",
        base_impact=0.5, base_urgency=0.4, actions=["investigate", "request_due_diligence"],
        dependencies=["master-v1"], description="Balance inconsistency (equity > total assets)."),

    # ── ownership ──
    "ownership.foreign_parent": dict(category="ownership", polarity="neutral", severity="info",
        base_impact=0.4, base_urgency=0.2, actions=["analyze", "compare"],
        dependencies=["master-v1", "knowledge-graph-v1"], description="Ultimate parent outside Spain."),
    "ownership.group_member": dict(category="ownership", polarity="neutral", severity="info",
        base_impact=0.4, base_urgency=0.2, actions=["analyze"],
        dependencies=["master-v1", "knowledge-graph-v1"], description="Member of an ownership group (≥2 entities)."),
    "ownership.consolidator": dict(category="ownership", polarity="positive", severity="opportunity",
        base_impact=0.65, base_urgency=0.3, actions=["analyze", "compare", "contact"],
        dependencies=["master-v1", "knowledge-graph-v1"], description="Holds ≥2 investees (potential roll-up actor)."),
    "ownership.standalone": dict(category="ownership", polarity="neutral", severity="info",
        base_impact=0.45, base_urgency=0.2, actions=["analyze", "add_to_watchlist"],
        dependencies=["master-v1", "knowledge-graph-v1"], description="No parents/group (independent target)."),

    # ── market ──
    "market.outperforms_peers": dict(category="market", polarity="positive", severity="positive",
        base_impact=0.6, base_urgency=0.3, actions=["analyze", "compare", "add_to_watchlist"],
        dependencies=["financial-intelligence-v1"], description="EBITDA margin in top quartile vs peers."),
    "market.underperforms_peers": dict(category="market", polarity="negative", severity="warning",
        base_impact=0.5, base_urgency=0.4, actions=["analyze", "compare"],
        dependencies=["financial-intelligence-v1"], description="EBITDA margin in bottom quartile vs peers."),
    "market.fragmented_sector": dict(category="market", polarity="positive", severity="info",
        base_impact=0.5, base_urgency=0.2, actions=["analyze", "compare"],
        dependencies=["financial-intelligence-v1"], description="Highly fragmented sector (many comparable peers)."),

    # ── operational ──
    "operational.productivity_high": dict(category="operational", polarity="positive", severity="positive",
        base_impact=0.5, base_urgency=0.2, actions=["analyze", "compare"],
        dependencies=["financial-intelligence-v1"], description="Revenue per employee above threshold."),
    "operational.productivity_low": dict(category="operational", polarity="negative", severity="info",
        base_impact=0.4, base_urgency=0.3, actions=["analyze", "investigate"],
        dependencies=["financial-intelligence-v1"], description="Revenue per employee below threshold."),
    "operational.capital_intensive": dict(category="operational", polarity="neutral", severity="info",
        base_impact=0.4, base_urgency=0.2, actions=["analyze"],
        dependencies=["financial-intelligence-v1"], description="High capital intensity (assets/revenue)."),

    # ── corporate (change detection; requires master snapshot diffs) ──
    "corporate.officers_change": dict(category="corporate", polarity="neutral", severity="info",
        base_impact=0.4, base_urgency=0.4, actions=["investigate", "monitor"],
        dependencies=["master-v1"], requires_snapshot=True, description="Change in governing officers between snapshots."),
    "corporate.capital_change": dict(category="corporate", polarity="neutral", severity="info",
        base_impact=0.5, base_urgency=0.4, actions=["investigate"],
        dependencies=["master-v1"], requires_snapshot=True, description="Share capital change between snapshots."),
    "corporate.group_change": dict(category="corporate", polarity="neutral", severity="warning",
        base_impact=0.6, base_urgency=0.5, actions=["investigate", "monitor"],
        dependencies=["master-v1", "knowledge-graph-v1"], requires_snapshot=True,
        description="Entered/left an ownership group between snapshots."),
    "corporate.borme_event": dict(category="corporate", polarity="neutral", severity="info",
        base_impact=0.4, base_urgency=0.3, actions=["investigate", "monitor"],
        dependencies=["borme"], description="Corporate event registered in BORME within the lookback window."),
    "corporate.governance_change": dict(category="corporate", polarity="neutral", severity="warning",
        base_impact=0.55, base_urgency=0.5, actions=["investigate", "monitor"],
        dependencies=["borme"], description="Officer appointment, cessation, reelection or revocation in BORME (Q1: intent signal)."),
    "corporate.capital_movement": dict(category="corporate", polarity="neutral", severity="info",
        base_impact=0.5, base_urgency=0.4, actions=["investigate", "analyze"],
        dependencies=["borme"], description="Capital increase or decrease registered in BORME."),

    # ── risk (BORME distress signals; Q1) ──
    "risk.dissolution_signal": dict(category="risk", polarity="negative", severity="critical",
        base_impact=0.85, base_urgency=0.85, actions=["investigate", "request_due_diligence", "consult_advisor"],
        dependencies=["borme"], description="Dissolution, liquidation, extinction or insolvency event in BORME."),

    # ── opportunity (succession trigger; Q1 — first base signal in this category) ──
    # NOTE: age/birth date of administrators is NOT available in any connected source
    # (confirmed absent from BORME and Iberinform ingestion — see borme_bridge.py docstring).
    # Real proxy used instead: sole/majority administrator tenure (Iberinform `norm_officers`,
    # appointment_date is a real ingested field) at a standalone (non-group) company, optionally
    # corroborated by a recent BORME governance cessation event.
    "opportunity.succession_signal": dict(category="opportunity", polarity="positive", severity="opportunity",
        base_impact=0.7, base_urgency=0.35, actions=["analyze", "contact", "add_to_watchlist"],
        dependencies=["iberinform-officers", "master-v1"],
        description="Long-tenured sole/majority administrator at a standalone company (real proxy: "
                     "Iberinform appointment_date), optionally corroborated by a BORME cessation event."),

    # ── transaction (M&A; source pending) ──
    "transaction.ma_event": dict(category="transaction", polarity="neutral", severity="info",
        base_impact=0.7, base_urgency=0.6, actions=["investigate", "compare", "consult_advisor"],
        dependencies=["bme", "ma"], pending=True, description="M&A operation (source pending ingestion)."),
    "transaction.control_change": dict(category="transaction", polarity="neutral", severity="warning",
        base_impact=0.7, base_urgency=0.6, actions=["investigate", "consult_advisor"],
        dependencies=["bme", "ma"], pending=True, description="Change of control (source pending ingestion)."),
}


def catalog():
    """Public taxonomy catalog (exposed via /catalog). No UI concepts."""
    out = []
    for st, meta in SIGNAL_TYPES.items():
        out.append({
            "signal_type": st, "category": meta["category"],
            "severity": meta["severity"], "polarity": meta["polarity"],
            "default_actions": meta["actions"], "dependencies": meta["dependencies"],
            "pending_source": bool(meta.get("pending")),
            "requires_snapshot": bool(meta.get("requires_snapshot")),
            "description": meta["description"],
        })
    return out
