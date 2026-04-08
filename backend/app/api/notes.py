from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import CommunityNote

router = APIRouter()


class NoteCreate(BaseModel):
    article_id: UUID
    note_type: str  # "misleading", "missing_context", "factual_error", "praise"
    content: str
    evidence_urls: Optional[list[str]] = None
    verdict: Optional[str] = None


@router.get("/")
async def list_notes(
    article_id: Optional[UUID] = None,
    status: str = "approved",
    db: AsyncSession = Depends(get_db),
):
    q = select(CommunityNote).where(CommunityNote.status == status)
    if article_id:
        q = q.where(CommunityNote.article_id == article_id)
    q = q.order_by(CommunityNote.helpful_score.desc().nullslast())
    result = await db.execute(q)
    notes = result.scalars().all()
    return [
        {
            "id": str(n.id),
            "article_id": str(n.article_id),
            "note_type": n.note_type,
            "content": n.content,
            "verdict": n.verdict,
            "upvotes": n.upvotes,
            "downvotes": n.downvotes,
            "helpful_score": n.helpful_score,
            "created_at": n.created_at.isoformat(),
        }
        for n in notes
    ]


@router.post("/", status_code=201)
async def create_note(payload: NoteCreate, db: AsyncSession = Depends(get_db)):
    """Skapa community note. Auth implementeras i Fas 4."""
    raise HTTPException(
        status_code=501,
        detail="Community Notes auth implementeras i Fas 4.",
    )


@router.put("/{note_id}/vote")
async def vote_note(note_id: UUID, upvote: bool = True):
    """Rösta på en note. Auth implementeras i Fas 4."""
    raise HTTPException(
        status_code=501,
        detail="Röstning implementeras i Fas 4.",
    )
