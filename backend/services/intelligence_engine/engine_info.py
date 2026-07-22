"""Engine build & version metadata — computed once at startup.

Resolves git commit, build timestamp, environment and exposes engine identity.
Falls back gracefully when git is unavailable (e.g. inside a stripped container).
"""

import importlib
import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from .engine import ENGINE_VERSION
from .profiles import PROFILES


ENGINE_NAME = "Intelligence Engine"

# Capability modules — what this engine knows how to do beyond raw sources.
ENGINE_MODULES: List[str] = [
    "lineage",       # master.sources.* namespaces
    "cache",         # cache-first web source
    "queue",         # analysis_jobs scrape queue
    "enrichment",    # enrich_company(profile)
    "matching",      # entity_resolution.merge_into_master
]


def _resolve_git_commit() -> str:
    """Best-effort git commit SHA. Returns 'unknown' if git/repo not present."""
    candidates = [
        os.environ.get("GIT_COMMIT"),
        os.environ.get("COMMIT_SHA"),
        os.environ.get("RENDER_GIT_COMMIT"),
    ]
    for c in candidates:
        if c:
            return c[:12]
    try:
        repo_root = Path(__file__).resolve().parents[3]  # /app
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
        return out[:12] if out else "unknown"
    except Exception:
        return "unknown"


def _resolve_build_timestamp() -> str:
    """Build timestamp from env or process start time."""
    for k in ("BUILD_TIMESTAMP", "BUILD_TIME", "RELEASE_TIMESTAMP"):
        v = os.environ.get(k)
        if v:
            return v
    # Fallback: process start time
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_environment() -> str:
    for k in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        v = os.environ.get(k)
        if v:
            return v.lower()
    return "preview"


@lru_cache(maxsize=1)
def get_engine_identity() -> Dict:
    """Static identity computed once and cached for the process lifetime."""
    return {
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "build_timestamp": _resolve_build_timestamp(),
        "git_commit": _resolve_git_commit(),
        "environment": _resolve_environment(),
    }


def get_profile_names() -> List[str]:
    return list(PROFILES.keys())


def get_all_sources() -> List[str]:
    """Union of all sources declared across all profiles."""
    seen: List[str] = []
    for p in PROFILES.values():
        for s in p["sources"]:
            if s not in seen:
                seen.append(s)
    return seen


def get_source_meta(name: str) -> Dict:
    """Resolve a source's self-declared META descriptor (single source of truth).

    Each source module owns its metadata via a module-level `META` dict. We never
    keep a central registry — adding a source = adding its module + META + a
    profile entry. Missing keys fall back to safe defaults so the engine stays
    resilient if a source omits a field.
    """
    try:
        mod = importlib.import_module(f"services.intelligence_engine.sources.{name}")
        meta = dict(getattr(mod, "META", {}) or {})
    except Exception:
        meta = {}
    return {
        "display_name": meta.get("display_name", name),
        "collection": meta.get("collection"),
        "frequency": meta.get("frequency", "Bajo demanda"),
        "signal_source": meta.get("signal_source"),
        "audit_action": meta.get("audit_action"),
        "phase": meta.get("phase", "active"),
        "supports_manual_ingestion": bool(meta.get("supports_manual_ingestion", False)),
        "ingest_runner": meta.get("ingest_runner"),
        "supports_sample": bool(meta.get("supports_sample", bool(meta.get("collection")))),
        "queryable": bool(meta.get("queryable", bool(meta.get("collection")))),
        "actions": meta.get("actions", []),
        "sync_log": meta.get("sync_log"),
        "timestamp_field": meta.get("timestamp_field"),
        "display_fields": meta.get("display_fields", []),
        "hidden_fields": meta.get("hidden_fields", []),
        "field_labels": meta.get("field_labels", {}),
        "show_in_sidebar": bool(meta.get("show_in_sidebar", False)),
        "sidebar_group": meta.get("sidebar_group", "data"),
        "sidebar_dot": meta.get("sidebar_dot"),
    }


def get_all_source_meta() -> Dict[str, Dict]:
    """META for every engine source, keyed by source name. Fully dynamic."""
    return {n: get_source_meta(n) for n in get_all_sources()}


def get_capabilities() -> Dict:
    return {
        "profiles": get_profile_names(),
        "sources": get_all_sources(),
        "modules": list(ENGINE_MODULES),
    }
