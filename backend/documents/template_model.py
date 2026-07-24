"""Unified template model — one canonical template shape for the whole document module.

Resolves the two-systems split (DOCUMENT_STUDIO_UNIFICATION_PLAN.md):
  - `docstudio_templates`  : declarative sections (title/order/block_types/data_source/
                             ai_prompt/fields) — the format the Template Builder writes.
  - `document_templates`   : HTML/CSS templates with a draft->published lifecycle + versions.

Decision (§1): the unified template keeps the DECLARATIVE block format (so the Template
Builder can create templates without code) and the LIFECYCLE of the documents system
(status draft/published + version history). Narrative AI = Claude (decisión 4).

This module is ADDITIVE: it defines the canonical shape + normalizers + an idempotent
migration into a single `unified_templates` collection, leaving both legacy collections
untouched (Construir -> Validar -> Migrar -> Convivencia -> Retirar).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from models import new_id, now_iso
from docstudio import BLOCK_TYPES

# Document families from the catalog (§2 of the plan).
FAMILIES = ("A_company", "B_sector", "C_legal")

STATUSES = ("draft", "published")

# Narrative AI provider — decisión 4: la prosa la genera Claude.
DEFAULT_NARRATIVE_MODEL = "claude"
# Analysis stays deterministic (the engines compute the numbers, not the LLM).
DEFAULT_ANALYSIS_MODEL = "deterministic"

# Legacy narrative providers that must be remapped to Claude on normalization.
_LEGACY_NARRATIVE = {"openai", "gpt-5.2", "gpt-5.5", "gpt-4", "gpt-4o", "gpt", "", None}


def _narrative(raw_val: Optional[str]) -> str:
    """Map any legacy narrative model to Claude; preserve an explicit non-legacy value."""
    if raw_val is None:
        return DEFAULT_NARRATIVE_MODEL
    v = str(raw_val).strip().lower()
    if v in _LEGACY_NARRATIVE or v.startswith("gpt"):
        return DEFAULT_NARRATIVE_MODEL
    return raw_val


def _clean_sections(raw_sections) -> List[Dict]:
    """Normalize a sections list to the canonical declarative shape."""
    out = []
    for i, s in enumerate(raw_sections or [], start=1):
        if not isinstance(s, dict):
            continue
        block_types = [bt for bt in (s.get("block_types") or []) if bt in BLOCK_TYPES]
        out.append({
            "title": s.get("title", f"Sección {i}"),
            "order": s.get("order", i),
            "block_types": block_types,
            "data_source": s.get("data_source"),
            "ai_prompt": s.get("ai_prompt"),
            "fields": s.get("fields"),
        })
    out.sort(key=lambda x: x.get("order", 0))
    return out


def new_unified_template(name: str, *, family: str = "A_company",
                         category: str = "intelligence",
                         base_brand_id: Optional[str] = None,
                         sections: Optional[List[Dict]] = None,
                         supported_formats: Optional[List[str]] = None,
                         legal_disclaimer: Optional[str] = None,
                         narrative_model: Optional[str] = None,
                         provider: str = "custom", owner: Optional[str] = None,
                         template_id: Optional[str] = None) -> Dict:
    now = now_iso()
    return {
        "template_id": template_id or f"tpl_{new_id()[:12]}",
        "name": name,
        "description": "",
        "category": category,
        "family": family if family in FAMILIES else "A_company",
        "base_brand_id": base_brand_id,           # capa base (plataforma); overlay va por documento
        "narrative_model": _narrative(narrative_model),
        "analysis_model": DEFAULT_ANALYSIS_MODEL,
        "sections": _clean_sections(sections),
        "supported_formats": supported_formats or ["pdf", "pptx"],
        "legal_disclaimer": legal_disclaimer,
        "status": "draft",
        "version": 1,
        "visibility": "private",
        "provider": provider,
        "owner": owner,
        "source_system": "unified",
        "created_at": now,
        "updated_at": now,
    }


def normalize_template(raw: Dict, source: str) -> Dict:
    """Convert a legacy template (docstudio or documents) into the unified shape.

    Nothing is lost: legacy-only fields (html/css) are stashed under `legacy_render`.
    """
    tpl = new_unified_template(
        name=raw.get("name", "Plantilla"),
        category=raw.get("category") or raw.get("document_type") or "intelligence",
        base_brand_id=raw.get("base_brand_id") or raw.get("brand_id") or raw.get("default_brand_id"),
        sections=raw.get("sections"),
        supported_formats=raw.get("supported_formats"),
        legal_disclaimer=raw.get("legal_disclaimer"),
        narrative_model=raw.get("narrative_model"),
        provider=raw.get("provider") or ("builtin" if source else "custom"),
        owner=raw.get("owner") or raw.get("created_by"),
        template_id=raw.get("template_id"),
    )
    # Preserve lifecycle/versioning if the source already had it.
    tpl["description"] = raw.get("description", "")
    tpl["version"] = raw.get("version", 1)
    tpl["status"] = raw.get("status") if raw.get("status") in STATUSES else "draft"
    tpl["visibility"] = raw.get("visibility", "private")
    tpl["source_system"] = source
    tpl["analysis_model"] = raw.get("analysis_model") or DEFAULT_ANALYSIS_MODEL
    # Infer family from category when not explicit.
    if not raw.get("family"):
        cat = (tpl["category"] or "").lower()
        if cat in ("sector", "intelligence", "market"):
            tpl["family"] = "B_sector"
        elif cat in ("legal",):
            tpl["family"] = "C_legal"
        else:
            tpl["family"] = "A_company"
    # Stash legacy HTML/CSS render so nothing is lost during coexistence.
    if raw.get("html_template") or raw.get("css_template"):
        tpl["legacy_render"] = {
            "html_template": raw.get("html_template"),
            "css_template": raw.get("css_template"),
        }
    if raw.get("created_at"):
        tpl["created_at"] = raw["created_at"]
    return tpl


def validate_template(tpl: Dict) -> List[str]:
    """Return a list of problems ([] == valid)."""
    problems = []
    if not tpl.get("template_id"):
        problems.append("missing template_id")
    if not tpl.get("name"):
        problems.append("missing name")
    if tpl.get("status") not in STATUSES:
        problems.append(f"invalid status: {tpl.get('status')}")
    if tpl.get("family") not in FAMILIES:
        problems.append(f"invalid family: {tpl.get('family')}")
    if not isinstance(tpl.get("sections"), list):
        problems.append("sections must be a list")
    for s in tpl.get("sections", []):
        for bt in s.get("block_types", []):
            if bt not in BLOCK_TYPES:
                problems.append(f"unknown block_type '{bt}' in section '{s.get('title')}'")
    return problems


def publish(tpl: Dict) -> Dict:
    """Transition a template to published, bumping its version (caller snapshots)."""
    tpl["status"] = "published"
    tpl["version"] = tpl.get("version", 1) + 1
    tpl["updated_at"] = now_iso()
    return tpl


async def migrate_templates_to_unified(db) -> Dict:
    """Idempotent migration: read both legacy template collections, normalize, upsert
    into `unified_templates`. Legacy collections are left untouched. Safe to re-run.
    """
    counts = {"docstudio": 0, "documents": 0, "skipped_invalid": 0}
    now = now_iso()

    async def _upsert(raw, source, key):
        tpl = normalize_template(raw, source)
        if validate_template(tpl):
            counts["skipped_invalid"] += 1
            return
        await db.unified_templates.update_one(
            {"template_id": tpl["template_id"]},
            {"$set": {k: v for k, v in tpl.items() if k != "created_at"},
             "$setOnInsert": {"created_at": tpl.get("created_at", now)}},
            upsert=True,
        )
        counts[key] += 1

    async for raw in db.docstudio_templates.find({}, {"_id": 0}):
        await _upsert(raw, "docstudio", "docstudio")
    async for raw in db.document_templates.find({}, {"_id": 0}):
        await _upsert(raw, "documents", "documents")

    return counts
