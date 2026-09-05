"""Non-destructive field merge with provenance.

Each conflictable field keeps a list of candidates {source, value, observed_at, confidence}.
When sources disagree, ALL values are retained; the canonical value is chosen by
(confidence, source_priority, recency). Re-running a source replaces only that source's
candidate for the field — never destroys other sources' values.
"""

from typing import Dict, List, Optional, Any

SOURCE_PRIORITY = {"iberinform": 100, "web": 50, "bme": 60, "manual": 200}

# Fields managed with provenance (identity/classification/contact/size).
PROVENANCE_FIELDS = [
    "legal_name", "commercial_name", "cnae_code", "cnae_description",
    "web", "domain", "provincia", "municipio", "employees_total", "capital_social",
    # Fase 0 (2026-09-01) · campos de registro proyectados a master_companies. master_builder
    # los lee vía canonical(prov[...]); deben gestionarse con provenance como el resto o
    # prov[...] daría KeyError cuando llegan a None (bug latente hasta el primer rebuild).
    "domicilio", "sit_mercantil", "audited", "balance_model", "last_balance_year",
]


def _domain_from_web(web: Optional[str]) -> Optional[str]:
    if not web:
        return None
    d = web.strip().lower()
    for p in ("https://", "http://", "www."):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0].strip()
    return d or None


def merge_field(candidates: Optional[List[Dict]], source: str, value: Any,
                observed_at: str, confidence: float) -> List[Dict]:
    out = [c for c in (candidates or []) if c.get("source") != source]
    if value is not None and value != "":
        out.append({"source": source, "value": value, "observed_at": observed_at,
                    "confidence": round(confidence, 3)})
    return out


def canonical(candidates: Optional[List[Dict]]) -> Any:
    if not candidates:
        return None
    best = max(candidates, key=lambda c: (c.get("confidence", 0),
                                          SOURCE_PRIORITY.get(c.get("source"), 0),
                                          c.get("observed_at", "")))
    return best["value"]


def merge_provenance(existing_prov: Optional[Dict], source: str, fields: Dict[str, Any],
                     observed_at: str, confidence: float) -> Dict[str, List[Dict]]:
    prov = {k: list(v) for k, v in (existing_prov or {}).items()}
    for f in PROVENANCE_FIELDS:
        prov[f] = merge_field(prov.get(f), source, fields.get(f), observed_at, confidence)
    return prov
