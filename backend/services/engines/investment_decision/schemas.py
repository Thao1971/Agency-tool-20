"""Esquemas Pydantic de la API del Investment Decision Engine."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class BuyerProfileIn(BaseModel):
    type: str = "strategic"           # strategic|private_equity|family_office|search_fund|holding|corporate_venture
    mandate: Optional[Dict[str, Any]] = None
    capacity_eur: Optional[float] = None


class AnalysisRequestIn(BaseModel):
    opportunity_id: Optional[str] = None
    company_id: Optional[str] = None
    cif: Optional[str] = None
    buyer_profile: BuyerProfileIn = BuyerProfileIn()
    inputs: Optional[Dict[str, Any]] = None

    def to_engine(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id or self.company_id or self.cif,
            "company_id": self.company_id, "cif": self.cif,
            "buyer_profile": self.buyer_profile.dict(),
            "inputs": self.inputs or {},
        }
