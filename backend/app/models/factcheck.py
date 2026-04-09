import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy import TIMESTAMP, ARRAY
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import text
from typing import Optional

from app.database import Base


class FactCheck(Base):
    __tablename__ = "fact_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False, unique=True
    )
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    model_used: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[Optional[dict]] = mapped_column(JSONB)
    sourcing_score: Mapped[Optional[float]] = mapped_column(Float)
    framing_notes: Mapped[Optional[str]] = mapped_column(Text)
    bias_indicators: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    vs_source_profile: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()")
    )
