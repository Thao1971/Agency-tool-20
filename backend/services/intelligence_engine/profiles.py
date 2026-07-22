"""Enrichment profiles — declarative definition of which sources each product needs.

A profile is just a list of source names + optional config.
Sources are resolved at runtime to functions in `intelligence_engine.sources.*`.

Adding a new product = adding a new profile. No engine changes required.
"""

from typing import Dict, List, TypedDict


class ProfileDef(TypedDict):
    name: str
    description: str
    sources: List[str]


PROFILES: Dict[str, ProfileDef] = {
    # ── basic ────────────────────────────────────────────────────────────────
    # Universal data any product needs to identify and describe a company.
    "basic": {
        "name": "basic",
        "description": "Identity + web presence: description, logo, tags, contacts.",
        "sources": [
            "identity",          # companies_master core fields
            "web",               # scrape + LLM classification (description, logo, tags, contacts)
        ],
    },

    # ── valuo ────────────────────────────────────────────────────────────────
    # Valuation product: needs financials, market data, sector benchmark.
    "valuo": {
        "name": "valuo",
        "description": "basic + financials + market listing + sector benchmark + grants + territorial context.",
        "sources": [
            "identity",
            "web",
            "iberinform",        # revenue, employees, EBITDA
            "bme",               # ISIN, market cap, public company flag
            "economic_intel",    # sector revenue, trend, active companies
            "grants",            # public subsidies received (CDTI, ENISA, EU funds)
            "territorial",       # INE socio-economic context (income, growth)
        ],
    },

    # ── arroba ───────────────────────────────────────────────────────────────
    # Universal Search / M&A intelligence product. Everything.
    "arroba": {
        "name": "arroba",
        "description": "valuo + corporate signals + buyers + procurement + trade + IP + employment context.",
        "sources": [
            "identity",
            "web",
            "iberinform",
            "bme",
            "economic_intel",
            "borme",             # corporate events
            "procurement",       # PLACSP contracts
            "cnmv",              # investor entity + potential buyers
            "datacomex",         # foreign trade by CNAE
            "oepm",              # patents/trademarks (legacy stub)
            "grants",            # public subsidies (BDNS)
            "employment",        # Seg. Social + SEPE
            "territorial",       # INE
            "patentes",          # OEPM Fase 2 (stub)
            "catastro",          # Catastro Fase 2 (stub)
            "boe",               # BOE Fase 2 (stub)
        ],
    },
}


def get(profile_name: str) -> ProfileDef:
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown profile '{profile_name}'. Available: {list(PROFILES.keys())}")
    return PROFILES[profile_name]


def list_all() -> List[ProfileDef]:
    return list(PROFILES.values())
