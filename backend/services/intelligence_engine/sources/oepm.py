"""Source: OEPM — patents, trademarks, industrial designs (STUB).

Returns empty in Phase 1. Frozen until real Iberinform import (per user roadmap).
Lives here to keep the architecture symmetric — when OEPM is unfrozen,
only this file changes.
"""

from typing import Dict, Tuple


META = {
    "display_name": "OEPM (legacy stub)",
    "collection": None,
    "frequency": "Congelado (pendiente Iberinform real)",
    "signal_source": None,
    "audit_action": None,
    "phase": "stub",
    "supports_manual_ingestion": False,
    "ingest_runner": None,
    "show_in_sidebar": False,
    "sidebar_group": "data",
    "supports_sample": False,
    "queryable": False,
    "sidebar_dot": None,
}


async def enrich(master: Dict) -> Tuple[Dict, Dict]:
    return {}, {
        "source": "oepm",
        "found": False,
        "reason": "stub_pending_iberinform_real",
        "status": "frozen",
    }
