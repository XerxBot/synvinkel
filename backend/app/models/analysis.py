"""
SQLAlchemy-modeller för det analytiska provenienslagret.

Schema-design:
  analysis_runs                   — en körning av analysmodellen per person+tillfälle
  analysis_statement_contributions — vilka uttalanden + beta-vikter som låg till grund
  person_position_snapshots        — tidsstämplad politisk klassificering (auktoritativ)
  person_trajectories              — detekterade politiska förflyttningar över tid

source_persons.revealed_* fungerar som convenience-cache för senaste snapshot;
person_position_snapshots är sanningskällan.
"""
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import Boolean, Float, Integer, Text, text, Date
from sqlalchemy import TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalysisRun(Base):
    """
    En körning av analysmodellen för en specifik person.
    Skapar en länk från klassificeringen tillbaka till källmaterialet.
    """
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_persons.id", ondelete="CASCADE"), nullable=False
    )

    model_used: Mapped[str] = mapped_column(Text, nullable=False)
    source_platforms: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    statements_analyzed: Mapped[Optional[int]] = mapped_column(Integer)

    # API-kostnadsspårning
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    # Tidsspann för inkluderat källmaterial
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)

    status: Mapped[str] = mapped_column(Text, server_default=text("'completed'"))
    error_msg: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()")
    )


class AnalysisStatementContribution(Base):
    """
    Junction-tabell: vilka uttalanden bidrog till en analyskörning, med vilken beta-vikt.

    Svarar på: "Vilka exakta sources (url + id) och med vilka vikter genererade
    klassificeringen 'center-right' för person X?"

    Beta-vikt = weight_recency × weight_platform × weight_length (normaliserat)
    """
    __tablename__ = "analysis_statement_contributions"

    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    statement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person_statements.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Sammansatt beta-vikt (normaliserad)
    weight: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("1.0"))

    # Komponentvikter — transparens i beräkningsmodellen
    weight_recency: Mapped[Optional[float]] = mapped_column(Float)   # exp. avfall, t½=3 år
    weight_platform: Mapped[Optional[float]] = mapped_column(Float)  # riksdag=1.5, twitter=0.7
    weight_length: Mapped[Optional[float]] = mapped_column(Float)    # relativ längd vs median

    # Inkluderades i prompten (kan exkluderas pga token-gräns)?
    included: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # Registrerat politiskt signal för detta enskilda uttalande (om per-statement-analys körs)
    signal_leaning: Mapped[Optional[str]] = mapped_column(Text)
    signal_confidence: Mapped[Optional[float]] = mapped_column(Float)


class PersonPositionSnapshot(Base):
    """
    Tidsstämplad politisk klassificering för en person.

    Auktoritativ källa — source_persons.revealed_* är bara convenience-cache.
    Möjliggör historisk analys: "Vad stod person X för 2018 vs 2024?"

    Länkad till analysis_run → analysis_statement_contributions → person_statements.url
    ger full spårbarhet från klassificering till originalkälla.
    """
    __tablename__ = "person_position_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_persons.id", ondelete="CASCADE"), nullable=False
    )
    analysis_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id")
    )

    # Tidsspann för det analyserade källmaterialet
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)

    # Politiska dimensioner
    political_leaning: Mapped[Optional[str]] = mapped_column(Text)
    gal_tan_position: Mapped[Optional[str]] = mapped_column(Text)
    economic_position: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Float)

    # Avvikelse vs deklarerad institutionell position
    vs_declared_discrepancy: Mapped[Optional[str]] = mapped_column(Text)

    # Nyckelinsikter från analysen
    key_themes: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    analysis_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Metainformation
    source_platforms: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    statements_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Flagga: är detta den senaste/aktuella snapshoten?
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()")
    )


class PersonTrajectory(Base):
    """
    Detekterad politisk förflyttning mellan två tidpunkter.

    Beräknas automatiskt när ny PersonPositionSnapshot skapas om en tidigare finns.
    Möjliggör frågor som: "Har Carl Bildt förflyttat sig sedan riksdagsåren?",
    "Vilka politiker har gjort de största rörelseerna 2018-2024?"
    """
    __tablename__ = "person_trajectories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_persons.id", ondelete="CASCADE"), nullable=False
    )

    snapshot_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person_position_snapshots.id")
    )
    snapshot_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person_position_snapshots.id")
    )

    period_from: Mapped[Optional[date]] = mapped_column(Date)
    period_to: Mapped[Optional[date]] = mapped_column(Date)

    # Vilken dimension mäts (en rad per dimension)
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    # political_leaning | gal_tan | economic

    # Förflyttningens karaktär
    value_from: Mapped[Optional[str]] = mapped_column(Text)
    value_to: Mapped[Optional[str]] = mapped_column(Text)
    direction: Mapped[Optional[str]] = mapped_column(Text)
    # left | right | more_gal | more_tan | stable
    magnitude: Mapped[Optional[str]] = mapped_column(Text)
    # none | minor | moderate | significant

    trajectory_notes: Mapped[Optional[str]] = mapped_column(Text)
    significance: Mapped[Optional[str]] = mapped_column(Text)
    # routine | notable | major

    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()")
    )
