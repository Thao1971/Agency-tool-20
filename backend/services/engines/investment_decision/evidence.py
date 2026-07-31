"""resolve_evidence — adaptador de LECTURA a los Intelligence Engines existentes
(Boundary First: no recalcula, solo lee y normaliza). Combina el bundle real de
`docstudio.data_access.company_intelligence` con los `inputs` que traiga la request, y
calcula cobertura + motores usados/ausentes. Funciona con información parcial."""

from typing import Dict, Optional

# Entradas esperadas (para el cálculo de cobertura). Peso igual por simplicidad v1.
EXPECTED_INPUTS = [
    "identity", "kpis", "financials", "valuation", "signals",
    "evolution", "comparables", "assessment", "sector_intelligence", "documents",
]


async def resolve_evidence(request: Dict) -> Dict:
    """Devuelve {bundle, engines_used, engines_missing, coverage, source}."""
    inputs = dict(request.get("inputs") or {})
    bundle: Dict = {}
    engines_used, engines_missing = [], []
    source = "inputs"

    identifier = request.get("company_id") or request.get("cif")
    if identifier:
        try:
            from docstudio import data_access as DA
            b = await DA.company_intelligence(identifier)
            if b and b.get("found"):
                bundle = b
                source = "company_intelligence"
        except Exception:
            bundle = {}

    # Los inputs explícitos SOBRESCRIBEN/COMPLETAN el bundle (funciona sin BBDD).
    for k, v in inputs.items():
        if v is not None:
            bundle[k] = v

    # Normalización mínima: exponer atajos coherentes
    norm = {
        "identity": bundle.get("identity") or {},
        "kpis": bundle.get("kpis") or {},
        "financials": bundle.get("financials") or bundle.get("statements") or {},
        "valuation": bundle.get("valuation") or {},
        "signals": bundle.get("signals") or [],
        "evolution": bundle.get("evolution") or {},
        "comparables": bundle.get("comparables") or {},
        "assessment": bundle.get("assessment") or {},
        "sector_intelligence": bundle.get("sector_intelligence") or {},
        "documents": bundle.get("document_intelligence") or bundle.get("documents") or {},
        "engine_versions": bundle.get("engine_versions") or {},
        "found": bundle.get("found", bool(bundle)),
        "master_id": bundle.get("master_id"),
        "cif_normalized": bundle.get("cif_normalized"),
    }

    # Enriquecimiento best-effort (no cuenta para cobertura; da dato real a Market y Legal).
    section = (norm["identity"] or {}).get("cnae_section")
    if section and not norm.get("fragmentation"):
        try:
            from services.engines.investment.fragmentation import compute_fragmentation
            norm["fragmentation"] = await compute_fragmentation("cnae_section", section, limit_companies=800) or {}
        except Exception:
            norm["fragmentation"] = {}
    if norm.get("master_id") and not norm.get("ownership"):
        try:
            from database import db
            mdoc = await db.master_companies.find_one({"master_id": norm["master_id"]},
                                                      {"_id": 0, "ownership": 1})
            norm["ownership"] = (mdoc or {}).get("ownership") or {}
        except Exception:
            norm["ownership"] = {}
    # Overrides explícitos de inputs también para estas dos claves
    for k in ("fragmentation", "ownership"):
        if inputs.get(k) is not None:
            norm[k] = inputs[k]

    present = 0
    for key in EXPECTED_INPUTS:
        val = norm.get(key)
        has = bool(val) and (val != {} and val != [])
        if has:
            present += 1
            engines_used.append(key)
        else:
            engines_missing.append(key)
    coverage = round(present / len(EXPECTED_INPUTS), 4)

    return {"bundle": norm, "engines_used": engines_used,
            "engines_missing": engines_missing, "coverage": coverage, "source": source}
