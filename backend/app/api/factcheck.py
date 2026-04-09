"""
Faktakontroll-endpoints.
  POST /admin/articles/{id}/factcheck  — trigga analys (admin)
  GET  /articles/{id}/factcheck        — hämta sparad analys (publik)
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article, ArticleAnalysis
from app.models.factcheck import FactCheck
from app.models.organization import SourceOrganization
from app.models.user import User
from app.services.auth import require_admin
from app.services.factcheck import run_factcheck
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/articles/{article_id}/factcheck", status_code=201)
async def trigger_factcheck(
    article_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigga faktakontroll för en artikel. Admin-only.
    Kör synkront (väntar på Claude-svar) — kan ta 10–30 sekunder.
    Befintlig faktakontroll skrivs över.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY är inte konfigurerad på servern",
        )

    # Hämta artikel
    article = await db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(status_code=404, detail="Artikel hittades inte")

    if not article.full_text and not article.title:
        raise HTTPException(status_code=422, detail="Artikeln saknar text att analysera")

    # Hämta källprofil
    org = None
    if article.source_org_id:
        org = await db.scalar(
            select(SourceOrganization).where(SourceOrganization.id == article.source_org_id)
        )

    # Kör Claude-analys
    try:
        result = await run_factcheck(
            title=article.title,
            full_text=article.full_text or "",
            political_leaning=org.political_leaning if org else None,
            funding_category=org.funding_category if org else None,
            source_type=org.type if org else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Upsert — ta bort gammal om den finns
    existing = await db.scalar(
        select(FactCheck).where(FactCheck.article_id == article_id)
    )
    if existing:
        await db.delete(existing)
        await db.flush()

    fc = FactCheck(
        article_id=article_id,
        triggered_by=admin.id,
        model_used=settings.FACTCHECK_MODEL,
        claims=result.get("claims"),
        sourcing_score=result.get("sourcing_score"),
        framing_notes=result.get("framing_notes"),
        bias_indicators=result.get("bias_indicators") or [],
        vs_source_profile=result.get("vs_source_profile"),
        summary=result.get("summary"),
    )
    db.add(fc)
    await db.commit()
    await db.refresh(fc)

    return _serialize(fc)


@router.get("/articles/{article_id}/factcheck")
async def get_factcheck(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Hämta sparad faktakontroll för en artikel. Publik."""
    fc = await db.scalar(
        select(FactCheck).where(FactCheck.article_id == article_id)
    )
    if not fc:
        raise HTTPException(status_code=404, detail="Ingen faktakontroll hittad")
    return _serialize(fc)


def _serialize(fc: FactCheck) -> dict:
    return {
        "id": str(fc.id),
        "article_id": str(fc.article_id),
        "model_used": fc.model_used,
        "claims": fc.claims or [],
        "sourcing_score": fc.sourcing_score,
        "framing_notes": fc.framing_notes,
        "bias_indicators": fc.bias_indicators or [],
        "vs_source_profile": fc.vs_source_profile,
        "summary": fc.summary,
        "created_at": fc.created_at.isoformat(),
    }
