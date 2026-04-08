from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.article import Article, ScrapeJob
from app.models.organization import SourceOrganization
from app.models.topic import Topic
from app.models.user import CommunityNote, User
from app.services.auth import require_admin
from app.tasks.scrape import SCRAPER_REGISTRY, run_scrape_job

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


@router.get("/scrape-jobs/sources")
async def list_scrape_sources():
    """Visa tillgängliga source_slugs för scraping."""
    return {"sources": list(SCRAPER_REGISTRY.keys())}


@router.post("/scrape-jobs", status_code=202)
async def trigger_scrape(
    payload: ScrapeJobRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigga ett scraping-jobb. Körs asynkront i bakgrunden."""
    if payload.source_slug not in SCRAPER_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Okänd källa '{payload.source_slug}'. Tillgängliga: {list(SCRAPER_REGISTRY)}",
        )

    job = ScrapeJob(
        source_name=payload.source_slug,
        status="queued",
        config={"limit": payload.limit},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(
        run_scrape_job,
        job_id=job.id,
        source_slug=payload.source_slug,
        limit=payload.limit,
    )

    return {
        "job_id": str(job.id),
        "status": "queued",
        "source": payload.source_slug,
        "limit": payload.limit,
        "message": f"Jobb skapat för '{payload.source_slug}'. Körs i bakgrunden.",
    }


@router.get("/scrape-jobs/{job_id}")
async def get_scrape_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """Hämta status för ett specifikt scrape-jobb."""
    job = await db.scalar(select(ScrapeJob).where(ScrapeJob.id == job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Jobb hittades inte")
    return {
        "id": str(job.id),
        "source_name": job.source_name,
        "status": job.status,
        "articles_found": job.articles_found,
        "articles_new": job.articles_new,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "errors": job.errors,
    }


@router.get("/notes/pending")
async def list_pending_notes(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Hämta alla pending notes för moderering."""
    result = await db.execute(
        select(CommunityNote)
        .where(CommunityNote.status == "pending")
        .order_by(CommunityNote.created_at.asc())
    )
    notes = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "article_id": str(n.article_id),
            "note_type": n.note_type,
            "content": n.content,
            "evidence_urls": n.evidence_urls or [],
            "created_at": n.created_at.isoformat(),
        }
        for n in notes
    ]


@router.put("/notes/{note_id}/review")
async def review_note(
    note_id: UUID,
    verdict: str,
    review_notes: str = "",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Moderera en community note (admin only)."""
    result = await db.execute(select(CommunityNote).where(CommunityNote.id == note_id))
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note hittades inte")
    note.status = verdict  # "approved" / "rejected"
    note.review_notes = review_notes
    note.reviewed_at = datetime.now(timezone.utc)
    note.reviewed_by = admin.id
    await db.commit()
    return {"id": str(note_id), "status": verdict}
