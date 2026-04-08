import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))


class ArticleTopic(Base):
    __tablename__ = "article_topics"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relevance_score: Mapped[Optional[float]] = mapped_column(Float)
