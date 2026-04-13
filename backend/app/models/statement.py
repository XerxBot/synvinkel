import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Float, Integer, Text, text
from sqlalchemy import TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PersonStatement(Base):
    """
    Ett enskilt uttalande av en känd person — hämtat från riksdagen, sociala medier,
    blogg, pressrelease eller intervju. Används för att bygga personens 'revealed position'.
    """
    __tablename__ = "person_statements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_persons.id", ondelete="CASCADE"), nullable=False
    )
    # riksdag | twitter | facebook | blog | press_release | party_web | interview | news
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    # Per-statement analysis (populated by analyze_persons pipeline)
    stmt_leaning: Mapped[Optional[str]] = mapped_column(Text)
    stmt_gal_tan: Mapped[Optional[str]] = mapped_column(Text)
    stmt_confidence: Mapped[Optional[float]] = mapped_column(Float)
    stmt_topics: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
