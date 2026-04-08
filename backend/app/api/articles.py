from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article
from app.schemas.article import ArticleDetail, ArticleResponse

router = APIRouter()


@router.get("/", response_model=list[ArticleResponse])
async def list_articles(
    source_slug: Optional[str] = None,
    topic: Optional[str] = None,
    article_type: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    q = select(Article).order_by(Article.published_at.desc()).limit(limit).offset(offset)
    if article_type:
        q = q.where(Article.article_type == article_type)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Artikel hittades inte")
    return article
