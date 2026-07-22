"""Backward-compatibility shim — M1 coexistence (Sprint 8.2).

The legacy master-record signal computation (companies_master: signals[], signal_score,
signal_similarity) was relocated **byte-for-byte** to
`services.engines.signal.master_signals` during migration M1. This module re-exports its
public symbols so any remaining importer of `services.signal_engine` keeps working with an
identical observable contract.

This is the COEXISTENCE phase of Construir → Validar → Migrar → Convivencia → Monitorizar →
Retirar. Scheduled for RETIREMENT once no importer references this path
(see LEGACY_MIGRATION_PLAN.md). Do NOT add new imports from here — use
`services.engines.signal.master_signals`.
"""

from services.engines.signal.master_signals import (  # noqa: F401  (re-export)
    compute_signals,
    rebuild_signals,
    signal_similarity,
)

__all__ = ["compute_signals", "rebuild_signals", "signal_similarity"]
