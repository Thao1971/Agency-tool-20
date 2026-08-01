"""V2-02 — Public Company / Identity capability (arroba.v2).

Read-only projection of the canonical Master Record identity for the Empresa Ficha header
(COMP-1001/1002/1003). Auth: X-API-Key. Does NOT expose the admin /master/* routes.
Never invents fields: absent data is returned as null. Fully typed response (OpenAPI schema).
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from database import db
from services.service_auth import require_service_key
from services.data_layer.normalize import normalize_cif, name_key

router = APIRouter(prefix="/api/v2/company-intelligence", tags=["company-intelligence (v2)"])

CAPABILITY_VERSION = "company-intelligence-v2"


class CompanyIdentityRequest(BaseModel):
    identifier: str = Field(..., description="master_id o cif_normalized", examples=["B59022921"])


class SourceRef(BaseModel):
    source: Optional[str] = Field(None, examples=["iberinform"])
    external_id: Optional[str] = Field(None, examples=["B59022921"])
    source_version: Optional[str] = Field(None, examples=["20260519"])
    ingested_at: Optional[str] = Field(None, examples=["2026-07-04T19:45:10Z"])


class CnaeRef(BaseModel):
    code: Optional[str] = Field(None, examples=["4941"])
    description: Optional[str] = Field(None, examples=["Transporte de mercancías por carretera"])
    section: Optional[str] = Field(None, examples=["H"])
    division: Optional[str] = Field(None, examples=["49"])


class CompanyIdentityResponse(BaseModel):
    master_id: str = Field(..., examples=["mc_457c000acfd3"])
    cif: Optional[str] = Field(None, examples=["B59022921"])
    legal_name: Optional[str] = Field(None, examples=["TRANSPORTS LA MUNTANYESA SA"])
    commercial_name: Optional[str] = Field(None)
    aliases: List[str] = Field(default_factory=list)
    legal_form: Optional[str] = Field(None, description="Forma jurídica (null si no verificable)")
    mercantile_status: Optional[str] = Field(None, description="Estado mercantil (null si no verificable)")
    activity_status: Optional[str] = Field(None, description="Situación de actividad (null si no verificable)")
    incorporation_date: Optional[str] = Field(None, description="Fecha de constitución (null si no verificable)")
    address: Optional[str] = Field(None)
    postal_code: Optional[str] = Field(None)
    locality: Optional[str] = Field(None, examples=["Barcelona"])
    province: Optional[str] = Field(None, examples=["Barcelona"])
    autonomous_community: Optional[str] = Field(None, description="null si no verificable")
    country: Optional[str] = Field(None, examples=["ES"])
    website: Optional[str] = Field(None)
    domain: Optional[str] = Field(None, examples=["lamuntanyesa.com"])
    capital_social: Optional[float] = Field(None, description="Capital social (null si no verificable)")
    employees_total: Optional[int] = Field(None, description="Nº empleados (null si no verificable)")
    cnae_primary: Optional[CnaeRef] = None
    cnae_secondary: List[CnaeRef] = Field(default_factory=list)
    activity: Optional[str] = Field(None)
    corporate_purpose: Optional[str] = Field(None)
    description: Optional[str] = Field(None, description="Solo si existe descripción con soporte; nunca texto inventado")
    sectors: List[str] = Field(default_factory=list)
    is_listed: Optional[bool] = Field(None, description="Cotizada (null si no verificable)")
    listed_market: Optional[str] = Field(None)
    record_status: Optional[str] = Field(None, examples=["active"])
    updated_at: Optional[str] = None
    sources: List[SourceRef] = Field(default_factory=list)
    provenance_fields: List[str] = Field(default_factory=list, description="Campos con procedencia trazada")
    data_coverage: dict = Field(default_factory=dict, description="Qué campos están presentes (true) o ausentes (false)")
    capability_version: str = CAPABILITY_VERSION


def _build(doc: dict) -> CompanyIdentityResponse:
    ident = doc.get("identity") or {}
    cls = doc.get("classification") or {}
    loc = doc.get("location") or {}
    contact = doc.get("contact") or {}
    size = doc.get("size") or {}
    cnae = None
    if cls.get("cnae_code") or cls.get("cnae_description"):
        cnae = CnaeRef(code=cls.get("cnae_code"), description=cls.get("cnae_description"),
                       section=cls.get("cnae_section"), division=cls.get("cnae_division"))
    sources = [SourceRef(source=s.get("source"), external_id=s.get("external_id"),
                         source_version=s.get("source_version"), ingested_at=s.get("ingested_at"))
               for s in (doc.get("sources") or [])]
    sectors = [cls["cnae_section"]] if cls.get("cnae_section") else []
    resp = CompanyIdentityResponse(
        master_id=doc["master_id"],
        cif=doc.get("cif_normalized") or ident.get("cif"),
        legal_name=ident.get("legal_name"),
        commercial_name=ident.get("commercial_name"),
        aliases=ident.get("aliases") or [],
        locality=loc.get("municipio"),
        postal_code=loc.get("codigo_postal"),
        province=loc.get("provincia"),
        country=loc.get("pais") or ident.get("country"),
        website=contact.get("web"),
        domain=contact.get("domain"),
        capital_social=size.get("capital_social"),
        employees_total=size.get("employees_total"),
        cnae_primary=cnae,
        activity=cls.get("cnae_description"),
        corporate_purpose=doc.get("objeto_social"),
        sectors=sectors,
        record_status=doc.get("status"),
        updated_at=doc.get("updated_at") or doc.get("built_at"),
        sources=sources,
        provenance_fields=sorted(list((doc.get("provenance") or {}).keys())),
    )
    present = {}
    for f in ["cif", "legal_name", "commercial_name", "legal_form", "mercantile_status",
              "activity_status", "incorporation_date", "locality", "province",
              "autonomous_community", "country", "website", "domain", "capital_social",
              "employees_total", "cnae_primary", "corporate_purpose", "is_listed"]:
        v = getattr(resp, f)
        present[f] = bool(v)
    resp.data_coverage = present
    return resp


@router.post("/identity",
             responses={200: {"model": CompanyIdentityResponse,
                              "description": "Identidad canónica pública de la empresa"}},
             summary="Identidad canónica pública de una empresa (COMP-1001/1002/1003)")
async def company_identity(req: CompanyIdentityRequest, _key=Depends(require_service_key)):
    doc = await db.master_companies.find_one(
        {"$or": [{"master_id": req.identifier}, {"cif_normalized": req.identifier}]}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="company not found in Master Layer")
    return _build(doc).model_dump()


class CompanyResolveRequest(BaseModel):
    cif: Optional[str] = Field(None, description="CIF a resolver (exacto, normalizado)", examples=["A87803862"])
    name: Optional[str] = Field(None, description="Nombre/razón social a resolver", examples=["Totalenergies"])
    limit: int = Field(10, ge=1, le=50, description="Máx. coincidencias para búsqueda por nombre")


class CompanyResolveMatch(BaseModel):
    master_id: str = Field(..., examples=["mc_457c000acfd3"])
    cif: Optional[str] = Field(None, examples=["A87803862"])
    legal_name: Optional[str] = None
    province: Optional[str] = None
    cnae_section: Optional[str] = None
    match_type: str = Field(..., description="cif_exact | name_exact | name_partial", examples=["cif_exact"])
    score: float = Field(..., description="1.0 exacto; <1.0 parcial", examples=[1.0])


class CompanyResolveResponse(BaseModel):
    query: dict = Field(..., description="Eco de la consulta (cif/name)")
    count: int = 0
    matches: List[CompanyResolveMatch] = Field(default_factory=list)
    capability_version: str = CAPABILITY_VERSION


def _match(doc: dict, match_type: str, score: float) -> CompanyResolveMatch:
    return CompanyResolveMatch(
        master_id=doc["master_id"], cif=doc.get("cif_normalized"),
        legal_name=(doc.get("identity") or {}).get("legal_name"),
        province=(doc.get("location") or {}).get("provincia"),
        cnae_section=(doc.get("classification") or {}).get("cnae_section"),
        match_type=match_type, score=score,
    )


_PROJ = {"master_id": 1, "cif_normalized": 1, "identity.legal_name": 1,
         "location.provincia": 1, "classification.cnae_section": 1}


@router.post("/resolve",
             responses={200: {"model": CompanyResolveResponse,
                              "description": "Resolución pública CIF/Nombre → master_id"}},
             summary="Resolver un CIF o nombre a master_id canónico (solo X-API-Key)")
async def resolve(req: CompanyResolveRequest, _key=Depends(require_service_key)):
    """Public resolver (CIF or name → master_id). No JWT, no /master/*, no Mongo access needed.

    CIF: exact match on the normalized CIF. Name: exact name_key first, then partial (diacritics/
    case-insensitive), ranked. Returns the canonical master_id + a brief identity for each match.
    """
    if not (req.cif or req.name):
        raise HTTPException(status_code=422, detail="provide 'cif' or 'name'")

    from services.company_resolver import resolve_company_query
    result = await resolve_company_query(cif=req.cif, name=req.name, limit=req.limit)
    matches = [CompanyResolveMatch(**m) for m in result["matches"]]

    return CompanyResolveResponse(query={"cif": req.cif, "name": req.name},
                           count=len(matches), matches=matches).model_dump()
