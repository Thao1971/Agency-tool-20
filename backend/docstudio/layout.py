"""Document layout control — add/remove/reorder modules, page breaks, per-document
brand overlay and color overrides.

This is the data-model embodiment of the layout-control requirement (el usuario debe
poder controlar la maquetación en todo momento: añadir/eliminar módulos, reordenar,
saltos de página, colores). Pure functions over a document dict — no DB, no mutation
of anything but the passed doc — so the editor endpoints load a doc, apply an
operation, and save.

Document shape:
    {
      "document_id": ..., "version": N,
      "sections": [ {"section_id","title","order","blocks":[block,...]}, ... ],
      "brand_id": "...",              # base (platform) brand
      "brand_overlay": {...},         # OPTIONAL client overlay (logo + colors), decisión 3
      "color_override": {...},        # OPTIONAL per-document color tweaks (layout control)
    }

PAGE-BREAK CONTRACT (dos reglas, para que el renderer no "líe" los saltos):
    1. Salto explícito  -> un bloque {"block_type": "page_break"} fuerza
       `break-before: page` en el render (nueva página a partir de ahí).
    2. Módulo indivisible -> CADA bloque se renderiza con `break-inside: avoid`,
       de modo que una tabla / tarjeta / KPI NUNCA se parte a mitad entre páginas.
    El renderer (ver pdf_export.render_document_html) implementa ambas; este módulo
    solo coloca los bloques page_break donde el usuario los pide.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from docstudio import page_break_block


# ══════════════════════════════════════════
# LOOKUPS
# ══════════════════════════════════════════

def _sections(doc: Dict) -> List[Dict]:
    return doc.setdefault("sections", [])


def find_section(doc: Dict, section_id: str) -> Dict:
    for s in _sections(doc):
        if s.get("section_id") == section_id:
            return s
    raise ValueError(f"Section not found: {section_id}")


def find_block(doc: Dict, block_id: str):
    """Return (section, block, index_in_section) for a block_id."""
    for s in _sections(doc):
        for i, b in enumerate(s.get("blocks", [])):
            if b.get("block_id") == block_id:
                return s, b, i
    raise ValueError(f"Block not found: {block_id}")


# ══════════════════════════════════════════
# SECTIONS (módulos de nivel superior)
# ══════════════════════════════════════════

def add_section(doc: Dict, section: Dict, index: Optional[int] = None) -> Dict:
    """Insert a section (built with docstudio.new_section) at `index` (end if None)."""
    secs = _sections(doc)
    if index is None or index >= len(secs):
        secs.append(section)
    else:
        secs.insert(max(0, index), section)
    return normalize_orders(doc)


def remove_section(doc: Dict, section_id: str) -> Dict:
    secs = _sections(doc)
    before = len(secs)
    doc["sections"] = [s for s in secs if s.get("section_id") != section_id]
    if len(doc["sections"]) == before:
        raise ValueError(f"Section not found: {section_id}")
    return normalize_orders(doc)


def rename_section(doc: Dict, section_id: str, title: str) -> Dict:
    find_section(doc, section_id)["title"] = title
    return doc


def reorder_sections(doc: Dict, ordered_section_ids: List[str]) -> Dict:
    """Reorder sections to match the given id order. Ids must be exactly the current set."""
    secs = _sections(doc)
    current = {s.get("section_id") for s in secs}
    if set(ordered_section_ids) != current:
        raise ValueError("reorder_sections: id set must match current sections exactly")
    by_id = {s["section_id"]: s for s in secs}
    doc["sections"] = [by_id[sid] for sid in ordered_section_ids]
    return normalize_orders(doc)


def normalize_orders(doc: Dict) -> Dict:
    """Re-sequence section `order` fields 1..N to match array order."""
    for i, s in enumerate(_sections(doc), start=1):
        s["order"] = i
    return doc


# ══════════════════════════════════════════
# BLOCKS (módulos dentro de una sección)
# ══════════════════════════════════════════

def add_block(doc: Dict, section_id: str, block: Dict, index: Optional[int] = None) -> Dict:
    """Add a module (block) to a section at `index` (end if None)."""
    section = find_section(doc, section_id)
    blocks = section.setdefault("blocks", [])
    if index is None or index >= len(blocks):
        blocks.append(block)
    else:
        blocks.insert(max(0, index), block)
    return doc


def remove_block(doc: Dict, block_id: str) -> Dict:
    section, _, idx = find_block(doc, block_id)
    section["blocks"].pop(idx)
    return doc


def move_block(doc: Dict, block_id: str, to_section_id: str, to_index: Optional[int] = None) -> Dict:
    """Move a block to another (or the same) section at `to_index`."""
    src_section, block, idx = find_block(doc, block_id)
    dest = find_section(doc, to_section_id)
    src_section["blocks"].pop(idx)
    dblocks = dest.setdefault("blocks", [])
    if to_index is None or to_index >= len(dblocks):
        dblocks.append(block)
    else:
        dblocks.insert(max(0, to_index), block)
    return doc


def reorder_blocks(doc: Dict, section_id: str, ordered_block_ids: List[str]) -> Dict:
    section = find_section(doc, section_id)
    blocks = section.get("blocks", [])
    current = {b.get("block_id") for b in blocks}
    if set(ordered_block_ids) != current:
        raise ValueError("reorder_blocks: id set must match section's blocks exactly")
    by_id = {b["block_id"]: b for b in blocks}
    section["blocks"] = [by_id[bid] for bid in ordered_block_ids]
    return doc


# ══════════════════════════════════════════
# PAGE BREAKS (regla 1 del contrato)
# ══════════════════════════════════════════

def insert_page_break(doc: Dict, section_id: str, index: Optional[int] = None) -> Dict:
    """Insert an explicit page-break module at `index` within a section."""
    return add_block(doc, section_id, page_break_block(), index)


def remove_page_breaks(doc: Dict, section_id: Optional[str] = None) -> Dict:
    """Remove all page_break blocks (from one section, or the whole doc if None)."""
    targets = [find_section(doc, section_id)] if section_id else _sections(doc)
    for s in targets:
        s["blocks"] = [b for b in s.get("blocks", []) if b.get("block_type") != "page_break"]
    return doc


# ══════════════════════════════════════════
# BRAND OVERLAY + COLOR OVERRIDE (capa cliente + colores por documento)
# ══════════════════════════════════════════

def set_brand_overlay(doc: Dict, overlay: Optional[Dict]) -> Dict:
    """Attach (or clear) the client brand overlay for this document (decisión 3).

    The overlay is composed over the base brand at render time via
    brand_unified.compose_brand — it is NOT baked into the document, so changing
    the base brand later still works.
    """
    if overlay:
        doc["brand_overlay"] = overlay
    else:
        doc.pop("brand_overlay", None)
    return doc


def set_color_override(doc: Dict, colors: Optional[Dict]) -> Dict:
    """Per-document color tweaks (layout control). Merges into any existing override;
    pass None or {} to clear entirely. None-valued keys are dropped (never blank)."""
    if not colors:
        doc.pop("color_override", None)
        return doc
    clean = {k: v for k, v in colors.items() if v is not None}
    existing = doc.get("color_override") or {}
    existing.update(clean)
    doc["color_override"] = existing
    return doc


def effective_overlay(doc: Dict) -> Dict:
    """Combine the client brand overlay + per-document color override into a single
    overlay dict ready for brand_unified.compose_brand. Per-document color override
    wins over the client overlay's colors (it's the most specific)."""
    overlay = dict(doc.get("brand_overlay") or {})
    color_override = doc.get("color_override") or {}
    if color_override:
        tokens = dict(overlay.get("tokens") or {})
        colors = dict(tokens.get("colors") or {})
        colors.update(color_override)
        tokens["colors"] = colors
        overlay["tokens"] = tokens
    return overlay
