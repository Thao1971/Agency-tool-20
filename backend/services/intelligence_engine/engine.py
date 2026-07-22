"""Intelligence Engine — Unified enrichment orchestrator.

Single entry point: enrich_company(master_company_id, profile)
"""

import asyncio
import importlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database import db
from . import profiles as profile_registry
from .master_provider import get_master_record

logger = logging.getLogger(__name__)

ENGINE_VERSION = "1.0.0"


async def enrich_company(
    master_company_id: str,
    profile: str = "basic",
    force_refresh: bool = False,  # reserved for Phase 2 (web re-scraping)
) -> Dict:
    """Run enrichment for a company according to a product profile.

    Args:
        master_company_id: companies_master.master_company_id
        profile: 'basic' | 'valuo' | 'arroba' (see profiles.py)
        force_refresh: re-run sources that have cached scrapes (Phase 2)

    Returns:
        {
            "master_company_id": str,
            "profile": str,
            "engine_version": str,
            "fields": {"web.description": "...", "iberinform.revenue_latest": ...},
            "sources_consulted": [{"source": "...", "found": bool, ...}, ...],
            "sources_with_data": [str],
            "duration_ms": int,
            "started_at": str,
            "completed_at": str,
        }
    """
    started = datetime.now(timezone.utc)

    pdef = profile_registry.get(profile)
    source_names = pdef["sources"]

    # Fetch master once (via internal coexistence provider — single public contract, M2).
    master = await get_master_record(master_company_id)
    if not master:
        return {
            "master_company_id": master_company_id,
            "profile": profile,
            "engine_version": ENGINE_VERSION,
            "error": "master_not_found",
            "fields": {},
            "sources_consulted": [],
            "sources_with_data": [],
            "duration_ms": 0,
            "started_at": started.isoformat().replace("+00:00", "Z"),
            "completed_at": started.isoformat().replace("+00:00", "Z"),
        }

    # Run all sources in parallel
    tasks = [_run_source(name, master) for name in source_names]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    fields: Dict = {}
    sources_meta: List[Dict] = []
    sources_with_data: List[str] = []
    for name, (src_fields, src_meta) in zip(source_names, results):
        sources_meta.append({**src_meta, "source": name})
        if src_fields:
            fields.update(src_fields)
            sources_with_data.append(name)

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)

    return {
        "master_company_id": master_company_id,
        "profile": profile,
        "engine_version": ENGINE_VERSION,
        "fields": fields,
        "sources_consulted": sources_meta,
        "sources_with_data": sources_with_data,
        "duration_ms": duration_ms,
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": finished.isoformat().replace("+00:00", "Z"),
    }


async def _run_source(name: str, master: Dict):
    """Dynamically import and run a source module's enrich(master) coroutine."""
    try:
        mod = importlib.import_module(f"services.intelligence_engine.sources.{name}")
        return await mod.enrich(master)
    except ModuleNotFoundError:
        logger.error(f"Intelligence Engine: source '{name}' not found")
        return {}, {"source": name, "found": False, "error": "module_not_found"}
    except Exception as e:
        logger.exception(f"Intelligence Engine: source '{name}' raised {type(e).__name__}")
        return {}, {"source": name, "found": False, "error": str(e)[:200]}


def list_profiles():
    """Public helper for API endpoints."""
    return profile_registry.list_all()


def get_profile_definition(name: str):
    return profile_registry.get(name)
