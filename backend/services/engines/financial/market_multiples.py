"""Real market multiples from the M&A Radar (Q6 — MVP scope: agencias de publicidad).

Today `financial/engine.py::valuation()` uses a hardcoded, explicitly-labeled
"inferred/reference" EV/EBITDA table by CNAE section (`_SECTION_EV_EBITDA`). The
strategic roadmap's Q6 asks to replace that with real, market-observed multiples from
the M&A Radar (`transactions_normalized` / `category_valuations`, see
`services/category_valuations.py`) — the gap it documents as G7.

Verified before writing this module (do not re-derive without re-checking the code):
the M&A Radar's deals are classified into Agency Tool/CIS's own marketing-agency
taxonomy (`category_valuations.CATEGORIES`: "Estrategia, Marca y Diseño", "Creatividad
y Producción", "Digital, Growth y Commerce", etc.) — NOT into Spain's general CNAE
nomenclature that `master_companies` uses. There is no deterministic CNAE->CIS-category
mapping anywhere in this codebase: a transaction's category is an LLM suggestion that
always requires human review (`transactions/classification.py::suggest_classification`,
`requires_human_review: True` on every response). Building a fine-grained CNAE<->CIS
mapping here would mean inventing category boundaries this module has no data to
justify — exactly the kind of unverified signal this project avoids.

MVP scope (deliberate, narrow, matches "empezar por agencias, ampliar después al resto
del mercado cuando tengamos múltiplos reales de otros sectores"): only companies whose
real CNAE code falls in Spain's official CNAE-2009/2025 Division 73 ("Publicidad y
estudios de mercado" — 73.11 agencias de publicidad, 73.12 servicios de representación
de medios, 73.20 estudios de mercado y encuestas de opinión) are considered in scope
for a REAL multiple. This is the one sector where a real-world, standard classification
(not an invented mapping) plausibly overlaps with the CIS marketing-agency taxonomy the
M&A Radar's deals are classified into. Every other CNAE section keeps using the
existing inferred reference exactly as before — this module never claims coverage it
cannot support with real data.

Extending coverage later requires either (a) a verified CNAE<->CIS-category crosswalk
for more sectors, or (b) the transaction->master_id identity bridge (`entity_bridge.py`)
so an individual company gets its own observed multiple instead of a pooled aggregate —
both explicitly out of scope here, left as documented follow-ups.
"""

from typing import Dict, Optional

from services import category_valuations as CV

MARKET_MULTIPLES_VERSION = "market-multiples-v1"

# Spain's official CNAE-2009/2025 Division 73 ("Publicidad y estudios de mercado").
MARKETING_AGENCY_CNAE_CODES = {"7311", "7312", "7320"}

MIN_SAMPLE_SIZE = CV.MIN_SAMPLE_SIZE


def is_marketing_agency(cnae_code: Optional[str]) -> bool:
    if not cnae_code:
        return False
    code = str(cnae_code).strip()
    return any(code == c or code.startswith(c) for c in MARKETING_AGENCY_CNAE_CODES)


async def real_multiple_for_company(cnae_code: Optional[str]) -> Optional[Dict]:
    """Returns a real, market-observed EV/EBITDA multiple ONLY for marketing-agency
    CNAE codes and only when the pooled M&A Radar sample meets MIN_SAMPLE_SIZE.
    Returns None otherwise — callers MUST keep their existing inferred-multiple
    fallback, this function never blocks or replaces it silently."""
    if not is_marketing_agency(cnae_code):
        return None
    return await CV.get_marketing_agency_aggregate(min_sample_size=MIN_SAMPLE_SIZE)
