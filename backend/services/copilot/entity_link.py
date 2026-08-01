"""Copilot entity linker (Boundary First).

Turns a free-text question into a canonical company entity by REUSING the canonical Company
Intelligence resolver (`services.company_resolver.resolve_company_query`) — the Copilot never
searches `master_companies` ad-hoc. Flow: text → CIF/name extraction → canonical resolver →
master_id. Decides between an unambiguous auto-resolution and a disambiguation prompt.

Everything is referenced internally by `master_id`; CIF and legal_name are resolution attributes.
Deterministic and fact-locked: it never invents an entity; if nothing resolves it says so.
"""

import re
from typing import Dict, List

from services.company_resolver import resolve_company_query
from services.copilot import intent as INTENT

# Spanish CIF (letter + 7 digits + control) or NIF (8 digits + letter). Validated later by normalize_cif.
_CIF_RE = re.compile(r"\b([A-Za-z]\d{7}[0-9A-Za-z]|\d{8}[A-Za-z])\b")


def extract_cif(text: str):
    if not text:
        return None
    m = _CIF_RE.search(text)
    return m.group(1) if m else None


def _entity(match: Dict) -> Dict:
    return {"master_id": match["master_id"], "cif": match.get("cif"),
            "name": match.get("legal_name") or "la compañía", "match_score": match.get("score")}


async def link(question: str) -> Dict:
    """Resolve the company mentioned in `question`.

    Returns {status, entity?, candidates?, mention?}:
      - "resolved":  a single confident match → entity {master_id, cif, name, match_score}
      - "ambiguous": several plausible companies → candidates [{master_id, cif, name, ...}]
      - "none":      no company recognised in the text
    """
    if not question:
        return {"status": "none"}

    # 1) Exact by CIF if one appears in the text.
    cif = extract_cif(question)
    if cif:
        r = await resolve_company_query(cif=cif)
        if r["count"] == 1:
            return {"status": "resolved", "entity": _entity(r["matches"][0]), "mention": cif}

    # 2) By name mentions, via the canonical resolver. Merge + dedupe by master_id.
    by_id: Dict[str, Dict] = {}
    mentions: List[str] = []
    for nm in INTENT.extract_entities(question):
        if len(nm) < 4:
            continue
        r = await resolve_company_query(name=nm)
        if r["matches"]:
            mentions.append(nm)
        for m in r["matches"]:
            prev = by_id.get(m["master_id"])
            if not prev or m["score"] > prev["score"]:
                by_id[m["master_id"]] = m

    cands = sorted(by_id.values(), key=lambda m: m["score"], reverse=True)
    if not cands:
        return {"status": "none"}
    # Unambiguous: a single company, or a clear exact match that dominates.
    exacts = [c for c in cands if c["score"] >= 1.0]
    if len(cands) == 1:
        return {"status": "resolved", "entity": _entity(cands[0]),
                "mention": mentions[0] if mentions else None}
    if len(exacts) == 1:
        return {"status": "resolved", "entity": _entity(exacts[0]),
                "mention": mentions[0] if mentions else None}
    return {"status": "ambiguous", "candidates": [_entity(c) for c in cands[:5]],
            "mention": mentions[0] if mentions else None}
