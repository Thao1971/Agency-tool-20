"""Entity Resolution coexistence provider (M3, DER7).

Single public contract: consumers call `resolve_entity_provider(...)` and never know which
engine served them. The active engine is chosen by the INTERNAL flag `ENTITY_RESOLUTION_SOURCE`
("legacy" default | "canonical"). Rollback is immediate/transparent by flipping the flag.

Default = legacy → byte-identical to the previous direct `resolve_entity` call (zero regression).
"""
import os
from typing import Dict, List, Optional

from services.entity_resolution import resolve_entity as _legacy_resolve

LEGACY = "legacy"
CANONICAL = "canonical"


def active_resolution_source() -> str:
    return os.environ.get("ENTITY_RESOLUTION_SOURCE", LEGACY).strip().lower() or LEGACY


async def resolve_entity_provider(
    legal_name: Optional[str] = None,
    commercial_name: Optional[str] = None,
    cif: Optional[str] = None,
    domain: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    source: str = "unknown",
    provincia: Optional[str] = None,
) -> Dict:
    if active_resolution_source() == CANONICAL:
        from services.data_layer.master.identity_resolver import resolve_identity
        return await resolve_identity(
            legal_name=legal_name, commercial_name=commercial_name, cif=cif, domain=domain,
            aliases=aliases, source=source, provincia=provincia)
    return await _legacy_resolve(
        legal_name=legal_name, commercial_name=commercial_name, cif=cif, domain=domain,
        aliases=aliases, source=source)
