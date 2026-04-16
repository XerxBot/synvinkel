from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    type: str
    website: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    political_leaning: Optional[str] = None
    gal_tan_position: Optional[str] = None
    economic_position: Optional[str] = None
    declared_ideology: Optional[str] = None
    primary_funder: Optional[str] = None
    funding_category: Optional[str] = None
    annual_budget_sek: Optional[int] = None
    parent_org: Optional[str] = None
    founded_year: Optional[int] = None
    country: str = "SE"
    is_active: bool = True
    classification_source: Optional[str] = None
    classification_confidence: str = "high"
    classification_notes: Optional[str] = None
    staff_bias_gal_tan: Optional[str] = None
    staff_bias_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationProfile(OrganizationResponse):
    """Extended profile with domain URLs for the /sources/{slug} endpoint."""
    domains: list[str] = []
