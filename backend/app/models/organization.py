import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceOrganization(Base):
    __tablename__ = "source_organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    website: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    logo_url: Mapped[Optional[str]] = mapped_column(Text)
    political_leaning: Mapped[Optional[str]] = mapped_column(Text)
    gal_tan_position: Mapped[Optional[str]] = mapped_column(Text)
    economic_position: Mapped[Optional[str]] = mapped_column(Text)
    declared_ideology: Mapped[Optional[str]] = mapped_column(Text)
    primary_funder: Mapped[Optional[str]] = mapped_column(Text)
    funding_category: Mapped[Optional[str]] = mapped_column(Text)
    annual_budget_sek: Mapped[Optional[int]] = mapped_column(Integer)
    parent_org: Mapped[Optional[str]] = mapped_column(Text)
    founded_year: Mapped[Optional[int]] = mapped_column(Integer)
    country: Mapped[str] = mapped_column(Text, server_default=text("'SE'"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    classification_source: Mapped[Optional[str]] = mapped_column(Text)
    classification_confidence: Mapped[str] = mapped_column(Text, server_default=text("'high'"))
    classification_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))


class SourcePerson(Base):
    __tablename__ = "source_persons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_organizations.id")
    )
    secondary_org_ids: Mapped[Optional[list]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    is_journalist: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_politician: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_researcher: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    party_affiliation: Mapped[Optional[str]] = mapped_column(Text)
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, server_default=text("NOW()"))
