"""Unified brand system — two-layer (white-label) brand model.

Layer 1 (base): PLATFORM brand — chosen by the active platform that generates the
document (arroba.com / BUD / Valuo / CIS). Rich design tokens (colors/fonts/cover/
closing), reusing the `documents/design_system.py` token format (the richer of the
two legacy models).

Layer 2 (overlay): CLIENT customization — the end client who downloads the report
applies THEIR OWN logo and, fundamentally, THEIR OWN colors on top of the platform
brand. The overlay only carries the keys the client sets; everything else falls
through to the platform base.

`compose_brand(base, overlay)` merges the two and returns a full brand dict that
`design_system.generate_css_tokens(...)` can render into CSS variables unchanged.

This module is ADDITIVE — it does not modify or migrate any existing collection.
Part of DOCUMENT_STUDIO_UNIFICATION_PLAN.md Fase 1 (decisión 3, marca en dos capas).
"""

from __future__ import annotations

import copy
from typing import Dict, Optional

from documents.design_system import BRANDS as _RICH_BRANDS


# ══════════════════════════════════════════
# LAYER 1 — PLATFORM BASE BRANDS (rich token format)
# ══════════════════════════════════════════
# BUD / CIS / Arroba come from the rich model already defined in design_system.py.
# Valuo did NOT exist in the rich format (only a thin 3-color stub in
# docstudio/templates.py) — defined here in the same rich structure, green pulse
# over a light editorial surface, consistent with the Arroba/CIS token shape.

_VALUO_BRAND = {
    "brand_id": "brand_valuo",
    "name": "Valuo.pro",
    "logo_text": "valuo",
    "logo_light": None,
    "logo_dark": None,
    "is_default": False,
    "tokens": {
        "colors": {
            "bg_primary": "#f9fbfa",
            "bg_surface": "#f1f5f3",
            "bg_surface_alt": "#e8efeb",
            "text_primary": "#12201b",
            "text_secondary": "#3f4a45",
            "text_muted": "#6f7b76",
            "text_subtle": "#c2ccc8",
            "accent": "#059669",
            "accent_text": "#FFFFFF",
            "border": "rgba(194,204,200,0.15)",
            "border_light": "rgba(194,204,200,0.10)",
            "badge_bg": "#f1f5f3",
            "badge_border": "rgba(194,204,200,0.15)",
            "badge_text": "#3f4a45",
            "tag_bg": "#059669",
            "tag_text": "#FFFFFF",
            "kpi_bg": "#FFFFFF",
            "kpi_value": "#059669",
            "kpi_label": "#6f7b76",
            "strengths_bg": "#059669",
            "strengths_text": "#FFFFFF",
            "risks_bg": "#f1f5f3",
            "risks_text": "#12201b",
            "risks_border": "rgba(194,204,200,0.15)",
            "table_header_bg": "#12201b",
            "table_header_text": "#f9fbfa",
            "table_row_alt": "#f1f5f3",
            "table_border": "rgba(194,204,200,0.10)",
            "disclaimer_border": "#059669",
            "disclaimer_bg": "#FFFFFF",
        },
        "fonts": {
            "heading": "'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif",
            "body": "'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif",
            "mono": "'JetBrains Mono', 'Courier New', Courier, monospace",
        },
        "cover": {
            "bg": "#059669",
            "text": "#FFFFFF",
            "subtitle_text": "rgba(255,255,255,0.7)",
            "meta_text": "rgba(255,255,255,0.5)",
            "brand_text": "#FFFFFF",
            "badge_text": "#FFFFFF",
            "badge_border": "rgba(255,255,255,0.4)",
        },
        "closing": {
            "brand_text": "#12201b",
            "tagline_text": "#6f7b76",
            "contact_text": "#3f4a45",
            "legal_text": "#c2ccc8",
            "legal_border": "rgba(194,204,200,0.15)",
        },
    },
}

# The 4 platform base brands, all in the rich token format.
PLATFORM_BRANDS: Dict[str, Dict] = {
    "brand_bud": _RICH_BRANDS["brand_bud"],
    "brand_cis": _RICH_BRANDS["brand_cis"],
    "brand_arroba": _RICH_BRANDS["brand_arroba"],
    "brand_valuo": _VALUO_BRAND,
}

# Which platform maps to which base brand. The active platform generating the
# document decides the default base (decisión 3).
PLATFORM_TO_BRAND = {
    "arroba": "brand_arroba",
    "arroba.com": "brand_arroba",
    "bud": "brand_bud",
    "bud_advisors": "brand_bud",
    "valuo": "brand_valuo",
    "valuo.pro": "brand_valuo",
    "cis": "brand_cis",
}

DEFAULT_PLATFORM_BRAND = "brand_bud"


def resolve_platform_brand(platform: Optional[str]) -> Dict:
    """Return the base (platform) brand for the active platform.

    `platform` is the app generating the document (arroba.com/bud/valuo/cis).
    Falls back to BUD if unknown/None.
    """
    if not platform:
        return copy.deepcopy(PLATFORM_BRANDS[DEFAULT_PLATFORM_BRAND])
    key = PLATFORM_TO_BRAND.get(str(platform).strip().lower())
    return copy.deepcopy(PLATFORM_BRANDS.get(key or "", PLATFORM_BRANDS[DEFAULT_PLATFORM_BRAND]))


# ══════════════════════════════════════════
# LAYER 2 — CLIENT OVERLAY
# ══════════════════════════════════════════
# The client who downloads the report may override:
#   - logo:   logo_text / logo_light / logo_dark
#   - colors: any subset of tokens.colors (fundamentally the accent/brand colors)
#   - fonts:  optionally tokens.fonts
# Only the keys present in the overlay override the base; the rest fall through.

# Keys a client overlay is allowed to touch at the top level.
_OVERLAY_TOP_KEYS = ("logo_text", "logo_light", "logo_dark", "name")


def _clean(d: Optional[Dict]) -> Dict:
    """Drop None values so an overlay key set to None never blanks a base value."""
    if not d:
        return {}
    return {k: v for k, v in d.items() if v is not None}


def compose_brand(base: Dict, overlay: Optional[Dict] = None) -> Dict:
    """Compose the final brand = platform base + client overlay.

    `overlay` shape (all optional):
        {
          "logo_text": "...", "logo_light": "...", "logo_dark": "...", "name": "...",
          "tokens": {"colors": {...}, "fonts": {...}, "cover": {...}, "closing": {...}}
        }

    Returns a full brand dict in the rich format, ready for
    design_system.generate_css_tokens(). Pure function — no DB, no mutation of inputs.
    """
    result = copy.deepcopy(base or {})
    ov = _clean(overlay or {})

    # Top-level logo/name overrides
    for k in _OVERLAY_TOP_KEYS:
        if k in ov:
            result[k] = ov[k]

    # Token overrides, section by section (colors/fonts/cover/closing), key by key.
    ov_tokens = (overlay or {}).get("tokens") or {}
    result.setdefault("tokens", {})
    for section in ("colors", "fonts", "cover", "closing"):
        sec_overrides = _clean(ov_tokens.get(section))
        if not sec_overrides:
            continue
        result["tokens"].setdefault(section, {})
        result["tokens"][section].update(sec_overrides)

    # Mark that a client overlay was applied (useful for audit / UI).
    if ov or ov_tokens:
        result["client_customized"] = True

    return result


def resolve_brand(platform: Optional[str] = None,
                   base_brand_id: Optional[str] = None,
                   client_overlay: Optional[Dict] = None) -> Dict:
    """One-call resolver: pick base (by explicit brand_id or by platform) + overlay.

    Priority for the base: explicit `base_brand_id` wins over `platform`.
    """
    if base_brand_id and base_brand_id in PLATFORM_BRANDS:
        base = copy.deepcopy(PLATFORM_BRANDS[base_brand_id])
    else:
        base = resolve_platform_brand(platform)
    return compose_brand(base, client_overlay)
