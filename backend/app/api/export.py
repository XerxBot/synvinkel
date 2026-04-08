"""
GET /api/v1/export/articles — bulk-export för forskare.
Stödjer JSON och CSV, filtrering på topic/source/datum/typ.
Max 1000 artiklar per request — paginera med offset.
"""
import csv
import io
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article

router = APIRouter()


@router.get("/articles")
async def export_articles(
    source_slug: Optional[str] = Query(None, description="t.ex. 'timbro'"),
    source_org_id: Optional[UUID] = None,
    topic: Optional[str] = Query(None, description="Topic slug, t.ex. 'klimat'"),
    article_type: Optional[str] = Query(None, description="'rapport', 'anforande', 'motion'"),
    party: Optional[str] = Query(None, description="Parti-slug som nämns i artikeln"),
    published_after: Optional[date] = None,
    published_before: Optional[date] = None,
    has_full_text: Optional[bool] = None,
    limit: int = Query(default=100, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    include_full_text: bool = Query(default=False, description="Inkludera full_text (tung payload)"),
    db: AsyncSession = Depends(get_db),
):
    conditions = []

    if source_org_id:
        conditions.append(Article.source_org_id == source_org_id)
    if source_slug:
        conditions.append(Article.data_source == source_slug)
    if article_type:
        conditions.append(Article.article_type == article_type)
    if published_after:
        conditions.append(Article.published_at >= published_after)
    if published_before:
        conditions.append(Article.published_at <= published_before)
    if has_full_text is True:
        conditions.append(Article.full_text.isnot(None))
    if has_full_text is False:
        conditions.append(Article.full_text.is_(None))
    if topic:
        # PostgreSQL: topics @> ARRAY['klimat']
        conditions.append(Article.topics.contains([topic]))
    if party:
        conditions.append(Article.mentioned_parties.contains([party]))

    q = (
        select(Article)
        .where(and_(*conditions) if conditions else True)
        .order_by(Article.scraped_at.desc())
        .limit(limit)
        .offset(offset)
    )
    articles = (await db.execute(q)).scalars().all()

    def serialize(a: Article) -> dict:
        d = {
            "id": str(a.id),
            "url": a.url,
            "title": a.title,
            "subtitle": a.subtitle,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "scraped_at": a.scraped_at.isoformat(),
            "source_org_id": str(a.source_org_id) if a.source_org_id else None,
            "data_source": a.data_source,
            "author_names": a.author_names,
            "article_type": a.article_type,
            "section": a.section,
            "word_count": a.word_count,
            "language": a.language,
            "topics": a.topics,
            "mentioned_parties": a.mentioned_parties,
            "mentioned_persons": a.mentioned_persons,
            "mentioned_orgs": a.mentioned_orgs,
            "sentiment_score": a.sentiment_score,
        }
        if include_full_text:
            d["full_text"] = a.full_text
        return d

    rows = [serialize(a) for a in articles]

    if format == "csv":
        if not rows:
            return Response(content="", media_type="text/csv")
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: ";".join(v) if isinstance(v, list) else v
                for k, v in row.items()
            })
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=synvinkel_export.csv"},
        )

    return {
        "meta": {
            "total_returned": len(rows),
            "offset": offset,
            "limit": limit,
            "filters": {k: v for k, v in {
                "source_slug": source_slug,
                "topic": topic,
                "article_type": article_type,
                "party": party,
                "published_after": str(published_after) if published_after else None,
                "published_before": str(published_before) if published_before else None,
            }.items() if v is not None},
        },
        "articles": rows,
    }
