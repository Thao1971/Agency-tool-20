"""Document Design System — Brand profiles, design tokens, and CSS generation."""

from typing import Dict, Optional


# ══════════════════════════════════════════
# DEFAULT BRAND PROFILES
# ══════════════════════════════════════════

BRANDS = {
    "brand_bud": {
        "brand_id": "brand_bud",
        "name": "BUD Advisors",
        "logo_text": "BUD",
        "logo_light": "https://customer-assets.emergentagent.com/job_intel-agency/artifacts/gixlqoqf_Logo_blanco.png",
        "logo_dark": "https://customer-assets.emergentagent.com/job_intel-agency/artifacts/sg763koz_bud.png",
        "is_default": True,
        "tokens": {
            "colors": {
                "bg_primary": "#000000",
                "bg_surface": "#0d0d0d",
                "bg_surface_alt": "#1a1a1a",
                "text_primary": "#FFFFFF",
                "text_secondary": "#CCCCCC",
                "text_muted": "#939393",
                "text_subtle": "#666666",
                "accent": "#F3D200",
                "accent_text": "#000000",
                "border": "#1a1a1a",
                "border_light": "#333333",
                "badge_bg": "#1a1a1a",
                "badge_border": "#333333",
                "badge_text": "#CCCCCC",
                "tag_bg": "#F3D200",
                "tag_text": "#000000",
                "kpi_bg": "#0d0d0d",
                "kpi_value": "#F3D200",
                "kpi_label": "#666666",
                "strengths_bg": "#F3D200",
                "strengths_text": "#000000",
                "risks_bg": "#1a1a1a",
                "risks_text": "#FFFFFF",
                "risks_border": "#333333",
                "table_header_bg": "#F3D200",
                "table_header_text": "#000000",
                "table_row_alt": "#0a0a0a",
                "table_border": "#1a1a1a",
                "disclaimer_border": "#F3D200",
                "disclaimer_bg": "#0d0d0d",
            },
            "fonts": {
                "heading": "'Montserrat', 'Helvetica Neue', Helvetica, Arial, sans-serif",
                "body": "'Montserrat', 'Helvetica Neue', Helvetica, Arial, sans-serif",
                "mono": "'JetBrains Mono', 'Courier New', Courier, monospace",
            },
            "cover": {
                "bg": "#000000",
                "text": "#FFFFFF",
                "subtitle_text": "#939393",
                "meta_text": "#939393",
                "brand_text": "#F3D200",
                "badge_text": "#F3D200",
                "badge_border": "#F3D200",
            },
            "closing": {
                "brand_text": "#FFFFFF",
                "tagline_text": "#666666",
                "contact_text": "#939393",
                "legal_text": "#555555",
                "legal_border": "#1a1a1a",
            }
        }
    },

    "brand_cis": {
        "brand_id": "brand_cis",
        "name": "CIS — Centro de Inteligencia Sectorial",
        "logo_text": "CIS",
        "logo_light": "https://customer-assets.emergentagent.com/job_intel-agency/artifacts/gixlqoqf_Logo_blanco.png",
        "logo_dark": "https://customer-assets.emergentagent.com/job_intel-agency/artifacts/sg763koz_bud.png",
        "is_default": False,
        # The Editorial Ledger — translated from CIS Design System
        # Primary gold (#E1C422) = precision-targeted accent, sparingly
        # Surface hierarchy via tonal layering — no 1px solid borders
        # Playfair Display (spirit/headlines) + Inter (truth/body)
        # Depth through light, not shadows — ambient shadows only
        "tokens": {
            "colors": {
                # Surface hierarchy (tonal layering — "stacked vellum")
                "bg_primary": "#FAF9F9",             # surface — the canvas
                "bg_surface": "#F3F1F0",             # surface-container-low
                "bg_surface_alt": "#ECE9E7",         # surface-container
                # Text — never pure black, always #1B1C1C (editorial softness)
                "text_primary": "#1B1C1C",           # on-surface / on-background
                "text_secondary": "#44474A",         # on-surface-variant
                "text_muted": "#74777B",             # outline
                "text_subtle": "#C3C6CB",            # outline-variant (ghost borders)
                # The Gold — "highlighter, not paint bucket"
                "accent": "#6D5E00",                 # primary (deep gold for text/accents)
                "accent_text": "#FFFFFF",            # on-primary
                # Borders — ghost borders only (outline-variant at 15% opacity)
                "border": "rgba(195,198,203,0.15)",  # ghost border
                "border_light": "rgba(195,198,203,0.10)",
                # Badges — surface tiers, no borders
                "badge_bg": "#F3F1F0",               # surface-container-low
                "badge_border": "rgba(195,198,203,0.15)",
                "badge_text": "#44474A",             # on-surface-variant
                # Tags — gold accent, restrained
                "tag_bg": "#E1C422",                 # primary-container (the gold)
                "tag_text": "#1B1C1C",               # dark text on gold
                # KPIs — white "signature" cards on surface, gold values
                "kpi_bg": "#FFFFFF",                 # surface-container-lowest (card lift)
                "kpi_value": "#6D5E00",              # primary (deep gold)
                "kpi_label": "#74777B",              # outline
                # Highlights — gold for strengths, tonal shift for risks
                "strengths_bg": "#6D5E00",           # primary (deep gold)
                "strengths_text": "#FFFFFF",         # on-primary
                "risks_bg": "#F3F1F0",               # surface-container-low (tonal shift)
                "risks_text": "#1B1C1C",             # on-surface
                "risks_border": "rgba(195,198,203,0.15)",
                # Tables — dark header for authority, ghost row borders
                "table_header_bg": "#1B1C1C",        # near-black (never pure #000)
                "table_header_text": "#FAF9F9",      # surface
                "table_row_alt": "#F3F1F0",          # surface-container-low
                "table_border": "rgba(195,198,203,0.10)",
                # Disclaimer — gold accent border, elevated card
                "disclaimer_border": "#E1C422",      # primary-container gold
                "disclaimer_bg": "#FFFFFF",          # surface-container-lowest
            },
            "fonts": {
                # Playfair Display = "The Spirit" (headlines, editorial anchors)
                # Inter = "The Truth" (body, data, labels)
                "heading": "'Playfair Display', Georgia, 'Times New Roman', serif",
                "body": "'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif",
                "mono": "'JetBrains Mono', 'Courier New', Courier, monospace",
            },
            "cover": {
                # Gradient: primary (#6D5E00) → primary-container (#E1C422) at 135°
                "bg": "#6D5E00",                     # primary (gradient applied in CSS)
                "text": "#FFFFFF",                   # on-primary
                "subtitle_text": "rgba(255,255,255,0.65)",
                "meta_text": "rgba(255,255,255,0.45)",
                "brand_text": "#E1C422",             # primary-container gold
                "badge_text": "#E1C422",             # gold badge
                "badge_border": "rgba(225,196,34,0.5)",
            },
            "closing": {
                "brand_text": "#1B1C1C",             # on-background (never pure black)
                "tagline_text": "#74777B",           # outline
                "contact_text": "#44474A",           # on-surface-variant
                "legal_text": "#C3C6CB",             # outline-variant
                "legal_border": "rgba(195,198,203,0.15)",
            }
        }
    },

    "brand_arroba": {
        "brand_id": "brand_arroba",
        "name": "Arroba",
        "logo_text": "arroba",
        "logo_light": None,
        "logo_dark": "https://customer-assets.emergentagent.com/job_intel-agency/artifacts/qq4e87kz_image.png",
        "is_default": False,
        # The Editorial Pulse — translated from Arroba Design Manifesto
        # Primary (#990417) = "The Pulse" — sparingly for high-impact accents
        # Surface hierarchy via tonal layering, no hard borders
        # IBM Plex Sans for brand DNA + Inter for legibility
        # Tonal depth over drop shadows
        "tokens": {
            "colors": {
                # Surface hierarchy (tonal layering — no-line rule)
                "bg_primary": "#fcf9f8",            # surface — the canvas
                "bg_surface": "#f6f3f2",             # surface_container_low — soft lift
                "bg_surface_alt": "#efeceb",         # surface_container — one tier up
                # Text — high-contrast on warm neutrals
                "text_primary": "#1b1c1c",           # on_surface — near-black
                "text_secondary": "#44474a",         # on_surface_variant
                "text_muted": "#74777b",             # outline
                "text_subtle": "#c3c6cb",            # outline_variant (ghost borders at 15% opacity)
                # The Pulse — crimson accent, used sparingly
                "accent": "#990417",                 # primary — THE signature color
                "accent_text": "#FFFFFF",            # on_primary
                # Borders — ghost borders only (outline_variant at low opacity)
                "border": "rgba(195,198,203,0.15)",  # ghost border
                "border_light": "rgba(195,198,203,0.10)",
                # Badges — secondary container system
                "badge_bg": "#f6f3f2",               # surface_container_low
                "badge_border": "rgba(195,198,203,0.15)",  # ghost
                "badge_text": "#44474a",             # on_surface_variant
                # Tags — chips: full roundedness, secondary_container
                "tag_bg": "#f6f3f2",                 # secondary_container
                "tag_text": "#44474a",               # on_secondary_container
                # KPIs — pulse accent on warm surface
                "kpi_bg": "#FFFFFF",                 # surface_container_lowest — card lift
                "kpi_value": "#990417",              # primary — the pulse
                "kpi_label": "#74777b",              # outline
                # Highlights — pulse for strengths, tonal shift for risks
                "strengths_bg": "#990417",           # primary
                "strengths_text": "#FFFFFF",         # on_primary
                "risks_bg": "#f6f3f2",               # surface_container_low
                "risks_text": "#1b1c1c",             # on_surface
                "risks_border": "rgba(195,198,203,0.15)",  # ghost
                # Tables — editorial, minimal
                "table_header_bg": "#1b1c1c",        # inverse — dark header
                "table_header_text": "#fcf9f8",      # inverse text
                "table_row_alt": "#f6f3f2",          # surface_container_low
                "table_border": "rgba(195,198,203,0.10)",  # ghost border
                # Disclaimer — pulse accent border
                "disclaimer_border": "#990417",      # primary
                "disclaimer_bg": "#FFFFFF",          # surface_container_lowest
            },
            "fonts": {
                # Dual-font philosophy: IBM Plex Sans (brand DNA) + Inter (legibility)
                "heading": "'IBM Plex Sans', 'Inter', 'Helvetica Neue', Arial, sans-serif",
                "body": "'Inter', 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif",
                "mono": "'IBM Plex Mono', 'JetBrains Mono', 'Courier New', monospace",
            },
            "cover": {
                # Signature gradient: primary to primary_container at 135deg
                "bg": "#990417",                     # primary (gradient applied in CSS)
                "text": "#FFFFFF",                   # on_primary
                "subtitle_text": "rgba(255,255,255,0.7)",
                "meta_text": "rgba(255,255,255,0.5)",
                "brand_text": "#FFFFFF",             # on_primary
                "badge_text": "#FFFFFF",
                "badge_border": "rgba(255,255,255,0.4)",
            },
            "closing": {
                "brand_text": "#1b1c1c",             # on_surface
                "tagline_text": "#74777b",           # outline
                "contact_text": "#44474a",           # on_surface_variant
                "legal_text": "#c3c6cb",             # outline_variant
                "legal_border": "rgba(195,198,203,0.15)",
            }
        }
    }
}


def generate_css_tokens(brand_id: str = "brand_bud", brand_data: Optional[Dict] = None) -> str:
    """Generate CSS custom properties from a brand profile."""
    brand = brand_data or BRANDS.get(brand_id, BRANDS["brand_bud"])
    tokens = brand.get("tokens", {})
    colors = tokens.get("colors", {})
    fonts = tokens.get("fonts", {})
    cover = tokens.get("cover", {})
    closing = tokens.get("closing", {})

    css_vars = [":root {"]
    for key, val in colors.items():
        css_vars.append(f"  --{key.replace('_', '-')}: {val};")
    for key, val in fonts.items():
        css_vars.append(f"  --font-{key}: {val};")
    for key, val in cover.items():
        css_vars.append(f"  --cover-{key.replace('_', '-')}: {val};")
    for key, val in closing.items():
        css_vars.append(f"  --closing-{key.replace('_', '-')}: {val};")
    css_vars.append(f"  --logo-text: '{brand.get('logo_text', 'BUD')}';")
    css_vars.append("}")

    # Logo image display rules
    has_logo_light = bool(brand.get("logo_light"))
    has_logo_dark = bool(brand.get("logo_dark"))
    if has_logo_light or has_logo_dark:
        css_vars.append(".logo-text { display: none !important; }")
        css_vars.append(".logo-img { display: inline-block !important; }")
    else:
        css_vars.append(".logo-text { display: inline-block !important; }")
        css_vars.append(".logo-img { display: none !important; }")

    return "\n".join(css_vars)


async def get_brand_from_db(brand_id: str, db) -> Optional[Dict]:
    """Get brand from MongoDB, fallback to hardcoded defaults."""
    if db:
        brand = await db.document_brand_profiles.find_one({"brand_id": brand_id}, {"_id": 0})
        if brand:
            return brand
    return BRANDS.get(brand_id)


def get_brand_or_default(brand_id: str = None) -> Dict:
    """Get brand data by ID (sync), fallback to default."""
    if brand_id and brand_id in BRANDS:
        return BRANDS[brand_id]
    return BRANDS["brand_bud"]
