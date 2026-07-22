from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone


def new_id():
    return str(uuid.uuid4())

def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── Auth ──
class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    token: str
    user_id: str
    email: str

class ApiKeyCreate(BaseModel):
    name: str

class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    active: bool
    created_at: str
    last_used_at: Optional[str] = None


# ── Scraping ──
class ScrapeRequest(BaseModel):
    url: str

class BulkScrapeRequest(BaseModel):
    urls: List[str]
    callback_url: Optional[str] = None


# ── Jobs ──
class JobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    url: str
    status: str
    bulk_job_id: Optional[str] = None
    result_id: Optional[str] = None
    retries: int = 0
    error_message: Optional[str] = None
    phase: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

class BulkJobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    total_urls: int
    processed: int
    succeeded: int
    failed: int
    status: str
    callback_url: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None


# ── Evidence ──
class EvidenceItem(BaseModel):
    id: str = Field(default_factory=new_id)
    result_id: str
    field: str
    evidence_type: str
    source_url: Optional[str] = None
    fragment: Optional[str] = None
    confidence: int = 0
    detected_by: str = "parser"
    created_at: str = Field(default_factory=now_iso)


# ── Agency Result ──
class FailedPage(BaseModel):
    url: str
    reason: str

class AgencyResultResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    job_id: str
    input_url: str
    company_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: List[str] = []
    has_awards: bool = False
    awards_evidence: List[str] = []
    main_clients: List[str] = []
    main_contact_name: Optional[str] = None
    main_contact_role: Optional[str] = None
    main_contact_email: Optional[str] = None
    phone: Optional[str] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    screenshot_path: Optional[str] = None
    candidate_pages: List[str] = []
    visited_pages: List[str] = []
    failed_pages: List[Dict[str, str]] = []
    skipped_pages: List[Dict[str, str]] = []
    confidence_overall: int = 0
    confidence_category: int = 0
    confidence_clients: int = 0
    confidence_contact: int = 0
    confidence_awards: int = 0
    confidence_address: int = 0
    confidence_description: int = 0
    taxonomy_version: Optional[str] = None
    status: str = "completed"
    review_status: str = "pending_review"
    validated: bool = False
    validated_by: Optional[str] = None
    validated_at: Optional[str] = None
    last_edited_by: Optional[str] = None
    last_edited_at: Optional[str] = None
    created_at: str = ""
    evidence: List[Dict[str, Any]] = []


class ResultUpdateRequest(BaseModel):
    company_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: Optional[List[str]] = None
    has_awards: Optional[bool] = None
    awards_evidence: Optional[List[str]] = None
    main_clients: Optional[List[str]] = None
    main_contact_name: Optional[str] = None
    main_contact_role: Optional[str] = None
    main_contact_email: Optional[str] = None
    phone: Optional[str] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


# ── Taxonomy ──
class TaxonomyCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    order: int = 0
    active: bool = True

class TaxonomyCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    active: Optional[bool] = None

class TaxonomySubcategoryCreate(BaseModel):
    category_id: str
    name: str
    definition: Optional[str] = None
    order: int = 0
    active: bool = True

class TaxonomySubcategoryUpdate(BaseModel):
    name: Optional[str] = None
    definition: Optional[str] = None
    category_id: Optional[str] = None
    order: Optional[int] = None
    active: Optional[bool] = None

class TaxonomyImportItem(BaseModel):
    name: str
    subcategories: List[str] = []

class TaxonomyImportRequest(BaseModel):
    categories: List[TaxonomyImportItem]
    version: str = "v1.0"


# ── Config ──
class ScraperConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = ""
    max_depth: int = 2
    max_pages: int = 10
    capture_internal_pages: bool = True
    priority_patterns: List[str] = [
        "about", "nosotros", "quienes-somos", "quien-somos",
        "servicios", "services", "work", "trabajos", "portfolio",
        "clientes", "clients", "casos", "case",
        "equipo", "team", "premios", "awards",
        "contacto", "contact"
    ]
    timeout_seconds: int = 30
    concurrency_limit: int = 3
    export_format: str = "json"
    callback_url: Optional[str] = None
    updated_at: Optional[str] = None

class ConfigUpdateRequest(BaseModel):
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    capture_internal_pages: Optional[bool] = None
    priority_patterns: Optional[List[str]] = None
    timeout_seconds: Optional[int] = None
    concurrency_limit: Optional[int] = None
    export_format: Optional[str] = None
    callback_url: Optional[str] = None


# ── Buyer Mandates (E1 — G1: Buyer Intelligence por mandato) ──
# Real, user-defined acquisition criteria — the entity the gap analysis said was missing.
# Matching (services/engines/recommendation/mandates.py) filters/scores master_companies
# against these fields; nothing here is a data source, only search criteria over existing data.
class BuyerMandateCreate(BaseModel):
    name: str
    mandate_type: str = "strategic"          # strategic | financial | roll_up
    buyer_master_id: Optional[str] = None    # the acquirer, if it's itself a platform company
    target_cnae_sections: Optional[List[str]] = None
    target_cnae_codes: Optional[List[str]] = None
    target_provincias: Optional[List[str]] = None
    revenue_min: Optional[float] = None
    revenue_max: Optional[float] = None
    ownership_preference: str = "any"        # any | standalone_only
    exclude_master_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

class BuyerMandateUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None             # active | paused | closed
    mandate_type: Optional[str] = None
    target_cnae_sections: Optional[List[str]] = None
    target_cnae_codes: Optional[List[str]] = None
    target_provincias: Optional[List[str]] = None
    revenue_min: Optional[float] = None
    revenue_max: Optional[float] = None
    ownership_preference: Optional[str] = None
    exclude_master_ids: Optional[List[str]] = None
    notes: Optional[str] = None
