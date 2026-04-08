import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    url: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
    source_org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_organizations.id")
    )
    author_ids: Mapped[Optional[list]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    author_names: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    article_type: Mapped[Optional[str]] = mapped_column(Text)
    section: Mapped[Optional[str]] = mapped_column(Text)
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(Text, server_default=text("'sv'"))
    topics: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    mentioned_parties: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    mentioned_persons: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    mentioned_orgs: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(768))
    data_source: Mapped[Optional[str]] = mapped_column(Text)
    scrape_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))


class ArticleAnalysis(Base):
    __tablename__ = "article_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False
    )
    source_political_leaning: Mapped[Optional[str]] = mapped_column(Text)
    source_funding_category: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(Text)
    claims_count: Mapped[Optional[int]] = mapped_column(Integer)
    sourced_claims_count: Mapped[Optional[int]] = mapped_column(Integer)
    statistical_claims_count: Mapped[Optional[int]] = mapped_column(Integer)
    statistical_verified: Mapped[Optional[bool]] = mapped_column(Boolean)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text)
    related_article_ids: Mapped[Optional[list]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    coverage_spectrum: Mapped[Optional[dict]] = mapped_column(JSONB)
    analysis_version: Mapped[str] = mapped_column(Text, server_default=text("'v0.1'"))
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    confidence_explanation: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    articles_found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    articles_new: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    errors: Mapped[Optional[dict]] = mapped_column(JSONB)
    config: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))


class DataSourceConfig(Base):
    __tablename__ = "data_source_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_organizations.id")
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schedule: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("NOW()"))
