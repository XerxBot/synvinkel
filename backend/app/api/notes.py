"""
Community Notes — skapa, rösta och lista noter per artikel.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import CommunityNote, NoteVote, User
from app.services.auth import get_current_user, get_optional_user

router = APIRouter()

NOTE_TYPES = {"misleading", "missing_context", "factual_error", "praise"}


class NoteCreate(BaseModel):
    article_id: UUID
    note_type: str
    content: str
    evidence_urls: Optional[list[str]] = None
    verdict: Optional[str] = None

    @field_validator("note_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in NOTE_TYPES:
            raise ValueError(f"note_type måste vara ett av: {NOTE_TYPES}")
        return v

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 20:
            raise ValueError("Noten måste vara minst 20 tecken")
        if len(v) > 2000:
            raise ValueError("Noten får inte överstiga 2000 tecken")
        return v

    @field_validator("evidence_urls")
    @classmethod
    def valid_urls(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v:
            return [u for u in v if u.startswith("http")][:5]
        return v


def _serialize_note(n: CommunityNote, user_vote: Optional[bool] = None) -> dict:
    return {
        "id": str(n.id),
        "article_id": str(n.article_id),
        "note_type": n.note_type,
        "content": n.content,
        "evidence_urls": n.evidence_urls or [],
        "verdict": n.verdict,
        "status": n.status,
        "upvotes": n.upvotes,
        "downvotes": n.downvotes,
        "helpful_score": n.helpful_score,
        "user_vote": user_vote,   # True=up, False=down, None=ej röstat
        "created_at": n.created_at.isoformat(),
    }


@router.get("")
async def list_notes(
    article_id: Optional[UUID] = None,
    status: str = "approved",
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(CommunityNote).where(CommunityNote.status == status)
    if article_id:
        q = q.where(CommunityNote.article_id == article_id)
    q = q.order_by(CommunityNote.helpful_score.desc().nullslast(), CommunityNote.created_at.desc())
    notes = (await db.execute(q)).scalars().all()

    # Hämta användarens röster om inloggad
    user_votes: dict[UUID, bool] = {}
    if current_user and notes:
        note_ids = [n.id for n in notes]
        votes_result = await db.execute(
            select(NoteVote).where(
                NoteVote.note_id.in_(note_ids),
                NoteVote.user_id == current_user.id,
            )
        )
        user_votes = {v.note_id: v.is_upvote for v in votes_result.scalars()}

    return [_serialize_note(n, user_votes.get(n.id)) for n in notes]


@router.post("", status_code=201)
async def create_note(
    payload: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Begränsa till 5 pending noter per användare
    pending_count = await db.scalar(
        select(CommunityNote)
        .where(
            CommunityNote.author_user_id == current_user.id,
            CommunityNote.status == "pending",
        )
    )
    if pending_count and False:  # disabled for now, just track
        pass

    note = CommunityNote(
        article_id=payload.article_id,
        author_user_id=current_user.id,
        note_type=payload.note_type,
        content=payload.content,
        evidence_urls=payload.evidence_urls,
        verdict=payload.verdict,
        status="pending",
        helpful_score=0.0,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


@router.post("/{note_id}/vote")
async def vote_note(
    note_id: UUID,
    is_upvote: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await db.scalar(select(CommunityNote).where(CommunityNote.id == note_id))
    if not note:
        raise HTTPException(status_code=404, detail="Note hittades inte")
    if note.author_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Du kan inte rösta på din egen note")

    # Befintlig röst?
    existing = await db.scalar(
        select(NoteVote).where(
            NoteVote.note_id == note_id,
            NoteVote.user_id == current_user.id,
        )
    )

    if existing:
        if existing.is_upvote == is_upvote:
            # Tar bort rösten om man röstar samma igen
            if existing.is_upvote:
                note.upvotes = max(0, note.upvotes - 1)
            else:
                note.downvotes = max(0, note.downvotes - 1)
            await db.delete(existing)
        else:
            # Byter röst
            if is_upvote:
                note.upvotes += 1
                note.downvotes = max(0, note.downvotes - 1)
            else:
                note.downvotes += 1
                note.upvotes = max(0, note.upvotes - 1)
            existing.is_upvote = is_upvote
    else:
        vote = NoteVote(note_id=note_id, user_id=current_user.id, is_upvote=is_upvote)
        db.add(vote)
        if is_upvote:
            note.upvotes += 1
        else:
            note.downvotes += 1

    # Uppdatera helpful_score: Wilson-konfidensintervall (förenklat)
    total = note.upvotes + note.downvotes
    note.helpful_score = (note.upvotes / total) if total > 0 else 0.0

    await db.commit()
    return {"upvotes": note.upvotes, "downvotes": note.downvotes, "helpful_score": note.helpful_score}


@router.delete("/{note_id}")
async def delete_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    note = await db.scalar(select(CommunityNote).where(CommunityNote.id == note_id))
    if not note:
        raise HTTPException(status_code=404, detail="Note hittades inte")
    if note.author_user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Inte din note")
    await db.delete(note)
    await db.commit()
    return {"deleted": True}
