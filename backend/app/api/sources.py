from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import SourceOrganization
from app.schemas.organization import OrganizationProfile, OrganizationResponse
from app.services.url_analyzer import DOMAIN_MAP

router = APIRouter()


@router.get("/", response_model=list[OrganizationResponse])
async def list_sources(
    type: Optional[str] = None,
    leaning: Optional[str] = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Lista alla klassificerade källor."""
    q = select(SourceOrganization)
    if active_only:
        q = q.where(SourceOrganization.is_active.is_(True))
    if type:
        q = q.where(SourceOrganization.type == type)
    if leaning:
        q = q.where(SourceOrganization.political_leaning == leaning)
    q = q.order_by(SourceOrganization.name)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{slug}", response_model=OrganizationProfile)
async def get_source(slug: str, db: AsyncSession = Depends(get_db)):
    """Detaljerad källprofil inkl. kopplade domäner."""
    result = await db.execute(
        select(SourceOrganization).where(SourceOrganization.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Källa hittades inte")

    # Collect domains that map to this slug
    domains = [domain for domain, s in DOMAIN_MAP.items() if s == slug]

    data = OrganizationProfile.model_validate(org)
    data.domains = sorted(domains)
    return data
