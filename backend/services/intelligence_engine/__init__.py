"""Intelligence Engine — Unified enrichment layer for all products (Valuo, Arroba, ...).

Single entry point: enrich_company(master_company_id, profile)
"""

from .engine import enrich_company, list_profiles, get_profile_definition

__all__ = ["enrich_company", "list_profiles", "get_profile_definition"]
