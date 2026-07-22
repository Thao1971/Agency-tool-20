"""BORME capability — Pydantic models for events, jobs, and API contracts."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from models import new_id, now_iso


class BormeFetchDayRequest(BaseModel):
    date: str  # YYYYMMDD

class BormeFetchRangeRequest(BaseModel):
    date_from: str  # YYYYMMDD
    date_to: str    # YYYYMMDD

class BormeEnrichCompanyRequest(BaseModel):
    company_id: Optional[str] = None
    cif: Optional[str] = None
    company_name: Optional[str] = None
    province: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

class BormeEnrichBatchRequest(BaseModel):
    companies: List[BormeEnrichCompanyRequest]

class BormeEventOut(BaseModel):
    source: str = "BORME"
    publication_date: str
    borme_number: Optional[str] = None
    official_identifier: str
    section: Optional[str] = None
    section_name: Optional[str] = None
    registry_province: Optional[str] = None
    entry_number: Optional[str] = None
    company_name_raw: str
    company_name_normalized: Optional[str] = None
    event_type: str
    event_subtype: Optional[str] = None
    event_title: Optional[str] = None
    event_text_raw: Optional[str] = None
    event_text_excerpt: Optional[str] = None
    pdf_url: Optional[str] = None
    idempotency_key: str
    match_method: Optional[str] = None
    confidence_match: Optional[float] = None
    company_id: Optional[str] = None
    requested_company_id: Optional[str] = None
    requested_cif: Optional[str] = None
    requested_name: Optional[str] = None
    created_at: str = ""
