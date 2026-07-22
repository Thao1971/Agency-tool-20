"""Unified read accessors for companies_master.

Skills read the canonical `classification.*` / `financials.*` first, falling back to
legacy top-level fields. This keeps public contracts immutable while sourcing the
richest available data after the Data Layer rebuild.
"""

from typing import Dict, List, Optional


def _web(doc: Dict) -> Dict:
    return (doc.get("sources") or {}).get("web") or {}


def name_of(doc: Dict) -> Optional[str]:
    cn = doc.get("commercial_names") or []
    return (doc.get("legal_name") or doc.get("normalized_name")
            or (cn[0] if cn else None) or _web(doc).get("company_name") or doc.get("domain"))


def sector_of(doc: Dict) -> Optional[str]:
    cls = doc.get("classification") or {}
    return (cls.get("sector") or _web(doc).get("category")
            or doc.get("sector") or doc.get("category_name"))


def category_of(doc: Dict) -> Optional[str]:
    cls = doc.get("classification") or {}
    return (cls.get("category") or _web(doc).get("category")
            or doc.get("category_name") or cls.get("sector") or doc.get("sector"))


def cnae_section_of(doc: Dict) -> Optional[str]:
    cls = doc.get("classification") or {}
    return cls.get("cnae_section") or doc.get("cnae_section")


def financials_latest(doc: Dict) -> Optional[Dict]:
    fin = doc.get("financials") or {}
    latest = fin.get("latest")
    if latest:
        return latest
    # legacy fallback from top-level iberinform fields
    if doc.get("revenue_latest") or doc.get("employees_latest"):
        return {"revenue": doc.get("revenue_latest"), "employees": doc.get("employees_latest"),
                "ebitda": None, "year": None}
    return None


def financials_history(doc: Dict) -> List[Dict]:
    return (doc.get("financials") or {}).get("history") or []


def employees_of(doc: Dict) -> Optional[float]:
    f = financials_latest(doc) or {}
    return f.get("employees") or doc.get("employees_latest")


def revenue_of(doc: Dict) -> Optional[float]:
    f = financials_latest(doc) or {}
    return f.get("revenue") or doc.get("revenue_latest")
