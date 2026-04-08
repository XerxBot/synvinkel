from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ArticleResponse(BaseModel):
    id: UUID
    url: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    published_at: Optional[datetime] = None
    scraped_at: datetime
    source_org_id: Optional[UUID] = None
    author_names: Optional[list[str]] = None
    article_type: Optional[str] = None
    section: Optional[str] = None
    summary: Optional[str] = None
    word_count: Optional[int] = None
    language: str = "sv"
    topics: Optional[list[str]] = None
    mentioned_parties: Optional[list[str]] = None
    sentiment_score: Optional[float] = None
    data_source: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisSummary(BaseModel):
    """Inbäddad analys i ArticleDetail."""
    source_political_leaning: Optional[str] = None
    source_funding_category: Optional[str] = None
    source_type: Optional[str] = None
    confidence_score: Optional[float] = None
    confidence_explanation: Optional[str] = None
    coverage_spectrum: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class ArticleDetail(ArticleResponse):
    """Full article with text — used for single-article endpoints."""
    full_text: Optional[str] = None
    mentioned_persons: Optional[list[str]] = None
    mentioned_orgs: Optional[list[str]] = None
    analysis: Optional[AnalysisSummary] = None
