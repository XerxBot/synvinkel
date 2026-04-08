from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article, ScrapeJob
from app.models.organization import SourceOrganization
from app.models.topic import Topic
from app.models.user import CommunityNote

router = APIRouter()


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    """Pipeline-status och nyckeltal."""
    article_count = await db.scalar(select(func.count(Article.id)))
    org_count = await db.scalar(select(func.count(SourceOrganization.id)))
    topic_count = await db.scalar(select(func.count(Topic.id)))
    pending_notes = await db.scalar(
        select(func.count(CommunityNote.id)).where(CommunityNote.status == "pending")
    )
    recent_jobs_result = await db.execute(
        select(ScrapeJob).order_by(ScrapeJob.created_at.desc()).limit(5)
    )
    recent_jobs = recent_jobs_result.scalars().all()

    return {
        "counts": {
            "articles": article_count,
            "organizations": org_count,
            "topics": topic_count,
            "pending_community_notes": pending_notes,
        },
        "recent_scrape_jobs": [
            {
                "id": str(j.id),
                "source_name": j.source_name,
                "status": j.status,
                "articles_found": j.articles_found,
                "articles_new": j.articles_new,
                "created_at": j.created_at.isoformat(),
            }
            for j in recent_jobs
        ],
    }


class ScrapeJobRequest(BaseModel):
    source_slug: str
    limit: int = 20


@router.post("/scrape-jobs", status_code=202)
async def trigger_scrape(payload: ScrapeJobRequest, db: AsyncSession = Depends(get_db)):
    """Trigga ett scraping-jobb. Task queue implementeras i Fas 1."""
    job = ScrapeJob(
        source_name=payload.source_slug,
        status="queued",
        config={"limit": payload.limit},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return {"job_id": str(job.id), "status": "queued", "message": "Jobb skapat. Task queue i Fas 1."}


@router.put("/notes/{note_id}/review")
async def review_note(
    note_id: UUID,
    verdict: str,
    review_notes: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Moderera en community note."""
    result = await db.execute(select(CommunityNote).where(CommunityNote.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Note hittades inte")
    note.status = verdict  # "approved" / "rejected"
    note.review_notes = review_notes
    note.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"id": str(note_id), "status": verdict}
