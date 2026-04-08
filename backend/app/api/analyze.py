"""
POST /api/v1/analyze — kärnfunktionen.
Tar en URL och returnerar avsändarprofil baserad på domänmappning.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import SourceOrganization
from app.services.url_analyzer import DOMAIN_MAP, extract_domain

router = APIRouter()


class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    url: str
    domain: str
    source_slug: str | None
    source: dict | None
    confidence: str
    message: str


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_url(payload: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """
    Analysera en URL och returnera källans politiska profil.
    Kärnfunktionen i Synvinkel.
    """
    domain = extract_domain(payload.url)
    slug = DOMAIN_MAP.get(domain)

    # Unknown domain
    if slug is None and domain not in DOMAIN_MAP:
        return AnalyzeResponse(
            url=payload.url,
            domain=domain,
            source_slug=None,
            source=None,
            confidence="none",
            message=f"Domänen '{domain}' finns inte i klassificeringsdatabasen.",
        )

    # Known domain explicitly mapped to None (okategoriserad)
    if slug is None:
        return AnalyzeResponse(
            url=payload.url,
            domain=domain,
            source_slug=None,
            source=None,
            confidence="low",
            message=f"Domänen '{domain}' är känd men saknar politisk klassificering.",
        )

    result = await db.execute(
        select(SourceOrganization).where(SourceOrganization.slug == slug)
    )
    org = result.scalar_one_or_none()

    if not org:
        return AnalyzeResponse(
            url=payload.url,
            domain=domain,
            source_slug=slug,
            source=None,
            confidence="low",
            message=f"Känd domän men organisationen '{slug}' saknas i databasen — kör seed.",
        )

    return AnalyzeResponse(
        url=payload.url,
        domain=domain,
        source_slug=org.slug,
        source={
            "name": org.name,
            "slug": org.slug,
            "type": org.type,
            "website": org.website,
            "political_leaning": org.political_leaning,
            "gal_tan_position": org.gal_tan_position,
            "economic_position": org.economic_position,
            "declared_ideology": org.declared_ideology,
            "funding_category": org.funding_category,
            "primary_funder": org.primary_funder,
            "classification_confidence": org.classification_confidence,
            "classification_notes": org.classification_notes,
            "classification_source": org.classification_source,
        },
        confidence=org.classification_confidence or "high",
        message="Källa identifierad.",
    )
