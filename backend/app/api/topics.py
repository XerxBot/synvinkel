from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.topic import Topic
from app.schemas.topic import TopicResponse

router = APIRouter()


@router.get("/", response_model=list[TopicResponse])
async def list_topics(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).order_by(Topic.name))
    return result.scalars().all()


@router.get("/{slug}", response_model=TopicResponse)
async def get_topic(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Topic).where(Topic.slug == slug))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Ämne hittades inte")
    return topic


@router.get("/{slug}/coverage")
async def topic_coverage(slug: str, db: AsyncSession = Depends(get_db)):
    """Artiklar om detta ämne fördelat per politisk lutning. Full impl i Fas 1."""
    result = await db.execute(select(Topic).where(Topic.slug == slug))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Ämne hittades inte")
    return {
        "topic": {"slug": topic.slug, "name": topic.name},
        "coverage": [],
        "note": "Full täckningsanalys implementeras i Fas 1 när tillräckligt data finns.",
    }
