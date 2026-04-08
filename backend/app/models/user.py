import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default=text("'user'"))
    reputation_score: Mapped[float] = mapped_column(Float, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))


class CommunityNote(Base):
    __tablename__ = "community_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    note_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_urls: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    verdict: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    upvotes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    downvotes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    helpful_score: Mapped[Optional[float]] = mapped_column(Float)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ)
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))
