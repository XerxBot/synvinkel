from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article, ArticleAnalysis
from app.schemas.article import AnalysisSummary, ArticleDetail, ArticleResponse

router = APIRouter()


@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    source_slug: Optional[str] = None,
    topic: Optional[str] = None,
    article_type: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(Article).order_by(Article.published_at.desc()).limit(limit).offset(offset)
    if source_slug:
        q = q.where(Article.data_source == source_slug)
    if article_type:
        q = q.where(Article.article_type == article_type)
    if topic:
        q = q.where(Article.topics.contains([topic]))
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: UUID, db: AsyncSession = Depends(get_db)):
    article = await db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(status_code=404, detail="Artikel hittades inte")

    analysis = await db.scalar(
        select(ArticleAnalysis).where(ArticleAnalysis.article_id == article_id)
    )

    result = ArticleDetail.model_validate(article)
    if analysis:
        result.analysis = AnalysisSummary.model_validate(analysis)
    return result
