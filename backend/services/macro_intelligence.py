"""Macro Intelligence — Semantic signal layer for macro-financial indicators.

Architecture: Agency Tool computes ALL semantics. Arroba/Valuo only consume.
This module is the SINGLE source of truth for trend/signal/impact interpretation.

Enums are fixed contracts — used by all consumers.
"""

# ══════════════════════════════════════════
# SEMANTIC ENUMS (stable contracts)
# ══════════════════════════════════════════

TREND_DIRECTION = {"up", "down", "stable"}
TREND_STRENGTH = {"weak", "moderate", "strong"}
IMPACT_TYPE = {
    "positive_for_financing", "negative_for_financing",
    "positive_for_valuation", "negative_for_valuation",
    "neutral", "mixed",
}
SEVERITY = {"low", "medium", "high", "critical"}
SIGNAL_TYPE = {
    "financing_conditions_improving", "financing_conditions_tightening",
    "rate_cut_cycle", "rate_hike_cycle", "rate_stable",
    "credit_expansion", "credit_contraction", "credit_stable",
    "valuation_pressure_increasing", "valuation_pressure_decreasing",
    "market_stabilizing", "market_uncertain",
}
MACRO_TAGS = {
    "macro", "interest_rates", "financing", "credit", "policy_rates",
    "euribor", "bce", "monetary_policy", "valuation_context",
}


def compute_semantic_signal(indicator_key: str, value: float, yoy_pct: float = None,
                             trend_dir: str = None, trend_str: str = None) -> dict:
    """Compute semantic signal for an indicator. Pure function, no DB access."""
    signal = {
        "indicator_key": indicator_key,
        "trend_direction": trend_dir or "stable",
        "trend_strength": trend_str or "weak",
        "impact": "neutral",
        "severity": "low",
        "signal": "market_stabilizing",
        "tags": ["macro"],
    }

    if indicator_key.startswith("euribor"):
        signal["tags"].extend(["interest_rates", "financing", "euribor"])

        if yoy_pct is not None:
            if yoy_pct < -5:
                signal["impact"] = "positive_for_financing"
                signal["signal"] = "financing_conditions_improving"
                signal["severity"] = "medium" if yoy_pct < -15 else "low"
            elif yoy_pct > 5:
                signal["impact"] = "negative_for_financing"
                signal["signal"] = "financing_conditions_tightening"
                signal["severity"] = "medium" if yoy_pct > 15 else "low"
            else:
                signal["impact"] = "neutral"
                signal["signal"] = "rate_stable"

        if trend_dir == "down":
            signal["impact"] = "positive_for_financing"
            if signal["signal"] == "market_stabilizing":
                signal["signal"] = "rate_cut_cycle"
        elif trend_dir == "up":
            signal["impact"] = "negative_for_financing"
            if signal["signal"] == "market_stabilizing":
                signal["signal"] = "rate_hike_cycle"

    elif indicator_key == "bce_main_rate":
        signal["tags"].extend(["policy_rates", "bce", "monetary_policy"])
        if trend_dir == "down":
            signal["impact"] = "positive_for_financing"
            signal["signal"] = "rate_cut_cycle"
        elif trend_dir == "up":
            signal["impact"] = "negative_for_financing"
            signal["signal"] = "rate_hike_cycle"
        else:
            signal["signal"] = "rate_stable"

    elif indicator_key == "credit_private_sector":
        signal["tags"].extend(["credit", "financing"])
        if yoy_pct is not None:
            if yoy_pct > 2:
                signal["impact"] = "positive_for_valuation"
                signal["signal"] = "credit_expansion"
            elif yoy_pct < -2:
                signal["impact"] = "negative_for_valuation"
                signal["signal"] = "credit_contraction"
            else:
                signal["signal"] = "credit_stable"

    # Valuation pressure inference
    if "positive_for_financing" in signal["impact"]:
        signal["tags"].append("valuation_context")

    return signal


def compute_macro_context(signals: list) -> dict:
    """Aggregate individual signals into a macro context summary."""
    ctx = {
        "interest_rate_trend": "stable",
        "financing_conditions": "stable",
        "valuation_pressure": "neutral",
        "market_liquidity_context": "stable",
        "overall_severity": "low",
    }

    financing_signals = [s for s in signals if "financing" in s.get("impact", "")]
    rate_signals = [s for s in signals if s["indicator_key"].startswith("euribor") or s["indicator_key"] == "bce_main_rate"]
    credit_signals = [s for s in signals if "credit" in s.get("signal", "")]

    # Interest rate trend (majority of rate signals)
    if rate_signals:
        dirs = [s["trend_direction"] for s in rate_signals]
        if dirs.count("down") > dirs.count("up"):
            ctx["interest_rate_trend"] = "declining"
        elif dirs.count("up") > dirs.count("down"):
            ctx["interest_rate_trend"] = "rising"

    # Financing conditions
    pos = sum(1 for s in financing_signals if "positive" in s.get("impact", ""))
    neg = sum(1 for s in financing_signals if "negative" in s.get("impact", ""))
    if pos > neg:
        ctx["financing_conditions"] = "improving"
    elif neg > pos:
        ctx["financing_conditions"] = "tightening"

    # Valuation pressure
    if ctx["financing_conditions"] == "improving":
        ctx["valuation_pressure"] = "supportive"
    elif ctx["financing_conditions"] == "tightening":
        ctx["valuation_pressure"] = "compressing"

    # Liquidity
    for s in credit_signals:
        if s.get("signal") == "credit_expansion":
            ctx["market_liquidity_context"] = "expanding"
        elif s.get("signal") == "credit_contraction":
            ctx["market_liquidity_context"] = "contracting"

    # Overall severity
    severities = [s.get("severity", "low") for s in signals]
    if "critical" in severities:
        ctx["overall_severity"] = "critical"
    elif "high" in severities:
        ctx["overall_severity"] = "high"
    elif severities.count("medium") > len(severities) / 2:
        ctx["overall_severity"] = "medium"

    return ctx
