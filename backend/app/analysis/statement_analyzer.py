"""
Analyserar insamlade uttalanden med Claude och bygger en 'revealed position'
per person — dvs vad de faktiskt säger snarare än vad deras partibok säger.

Proveniensmodell (v0.2):
  Varje analyskörning loggas i analysis_runs.
  Varje uttalandes bidrag (beta-vikt) loggas i analysis_statement_contributions.
  Resultatet sparas som PersonPositionSnapshot (auktoritativ tidsstämplad klassificering).
  source_persons.revealed_* hålls synkroniserade som convenience-cache.
  Politiska förflyttningar detekteras och sparas i person_trajectories.

Beta-vikt = weight_platform × weight_recency × weight_length (normaliserat)
  weight_platform: riksdag=1.5, interview=1.3, press_release=1.1, twitter=0.7, ...
  weight_recency: exp. avfall med halvliv 3 år (äldre uttalanden väger mindre)
  weight_length: relativ längd vs median (korta tweets väger mindre)

Kostnad: ~0.1–0.5 SEK per person (Claude Haiku-4-5 priser per april 2025).
"""
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone, date
from typing import Optional

import anthropic
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis import (
    AnalysisRun,
    AnalysisStatementContribution,
    PersonPositionSnapshot,
    PersonTrajectory,
)
from app.models.organization import SourcePerson
from app.models.statement import PersonStatement

logger = logging.getLogger(__name__)

ANALYSIS_MODEL = "claude-haiku-4-5-20251001"
MAX_CONTENT_TOKENS = 12_000   # ~9 000 ord
MAX_CHARS_PER_STATEMENT = 800  # trunkera långa anföranden

# ---------------------------------------------------------------------------
# Viktparametrar för beta-beräkning
# ---------------------------------------------------------------------------

PLATFORM_WEIGHTS: dict[str, float] = {
    "riksdag":       1.5,   # substantiella debattanföranden
    "interview":     1.3,   # direkta intervjusvar
    "press_release": 1.1,   # officiella pressmeddelanden
    "party_web":     1.0,   # partiets hemsida
    "blog":          1.0,   # bloggposter
    "news":          0.9,   # nyhetscitat
    "facebook":      0.8,   # Facebook-inlägg
    "twitter":       0.7,   # tweets (korta, reaktiva)
}
DEFAULT_PLATFORM_WEIGHT = 1.0
RECENCY_HALFLIFE_YEARS = 3.0   # halvliv för recency-vikten

# Politisk positions-skala för trajektori-beräkning
LEANING_SCALE: dict[str, int] = {
    "far-left": -3, "left": -2, "center-left": -1,
    "center": 0,
    "center-right": 1, "right": 2, "far-right": 3,
}
GAL_TAN_SCALE: dict[str, int] = {
    "gal": -2, "center-gal": -1, "center": 0, "center-tan": 1, "tan": 2,
}

_SYSTEM_PROMPT = """Du är en oberoende politisk analytiker specialiserad på svenska politiker och debattörer.
Du analyserar vad personer faktiskt säger och skriver — inte deras partibok eller institutionella roll.
Du identifierar den reella politiska positionen baserat på konkreta uttalanden.
Svara ALLTID med giltig JSON. Inga kommentarer utanför JSON."""

_PROMPT_TEMPLATE = """Analysera politisk position för: {name} ({title})

INSTITUTIONELL PROFIL (databas — kan vara föråldrad eller missvisande):
- Deklarerad lutning: {declared_leaning}
- GAL-TAN: {declared_gal_tan}
- Ekonomisk position: {declared_economic}
- Parti: {party}

INSAMLADE UTTALANDEN ({n_statements} st, plattformar: {platforms}, period: {period}):
{statements_block}

UPPGIFT:
Analysera den FAKTISKA politiska positionen baserat på uttalandena ovan.
Fokusera på:
- Konkreta ståndpunkter i sakfrågor (ekonomi, migration, klimat, säkerhet, välfärd, EU)
- Retorik och värdeladdade ordval
- Vem/vad de stödjer eller kritiserar
- Om de avviker från sin institutionella/historiska profil

Returnera EXAKT detta JSON (inga extra fält):
{{
  "revealed_political_leaning": "<far-left|left|center-left|center|center-right|right|far-right>",
  "revealed_gal_tan_position": "<gal|center-gal|center|center-tan|tan>",
  "revealed_economic_position": "<far-left|left|center-left|center|center-right|right>",
  "confidence": <0.0-1.0>,
  "discrepancy": "<none|minor|moderate|significant>",
  "key_themes": ["tema1", "tema2", "tema3"],
  "analysis_notes": "2-4 meningar som förklarar den faktiska positionen och eventuella avvikelser"
}}

Definitioner för discrepancy:
- none: faktisk position stämmer med institutionell
- minor: liten avvikelse i nyans eller ton
- moderate: tydlig skillnad på en axel
- significant: faktisk position skiljer sig markant från institutionell"""


# ---------------------------------------------------------------------------
# Viktberäkning
# ---------------------------------------------------------------------------

def _compute_weights(
    statements: list[PersonStatement],
) -> list[tuple[PersonStatement, float, float, float, float]]:
    """
    Beräkna beta-vikter för varje uttalande.
    Returnerar lista av (statement, weight_total, w_recency, w_platform, w_length).
    weight_total är normaliserad så att summan = 1.0 (bland inkluderade).
    """
    now = datetime.now(tz=timezone.utc)

    # Medianordräkning för längd-normalisering
    word_counts = [s.word_count or 0 for s in statements]
    median_wc = sorted(word_counts)[len(word_counts) // 2] if word_counts else 100
    median_wc = max(median_wc, 50)  # undvik division med noll

    raw: list[tuple[PersonStatement, float, float, float]] = []
    for stmt in statements:
        # Plattformsvikt
        w_platform = PLATFORM_WEIGHTS.get(stmt.platform, DEFAULT_PLATFORM_WEIGHT)

        # Tidsvikt — exponentiellt avfall
        if stmt.published_at:
            pub = stmt.published_at.replace(tzinfo=timezone.utc) if stmt.published_at.tzinfo is None else stmt.published_at
            years_ago = (now - pub).days / 365.25
            w_recency = math.pow(0.5, years_ago / RECENCY_HALFLIFE_YEARS)
        else:
            w_recency = 0.5  # okänt datum → halverat

        # Längdvikt — relativ till median, kappat vid 3×median
        wc = stmt.word_count or 0
        w_length = min(wc / median_wc, 3.0) / 3.0   # normaliserat 0–1

        raw.append((stmt, w_platform, w_recency, w_length))

    # Beräkna sammansatt råvikt och normalisera
    raw_totals = [wp * wr * max(wl, 0.1) for _, wp, wr, wl in raw]
    total = sum(raw_totals) or 1.0
    result = []
    for (stmt, wp, wr, wl), rt in zip(raw, raw_totals):
        result.append((stmt, rt / total, wr, wp, wl))

    return result


# ---------------------------------------------------------------------------
# Trajektori-detektering
# ---------------------------------------------------------------------------

def _leaning_to_int(leaning: Optional[str], scale: dict) -> Optional[int]:
    if not leaning:
        return None
    return scale.get(leaning.lower())


def _direction_from_delta(delta: int, dimension: str) -> str:
    if delta == 0:
        return "stable"
    if dimension == "gal_tan":
        return "more_gal" if delta < 0 else "more_tan"
    return "left" if delta < 0 else "right"


def _magnitude_from_delta(delta: int) -> str:
    if delta == 0:
        return "none"
    if abs(delta) == 1:
        return "minor"
    if abs(delta) == 2:
        return "moderate"
    return "significant"


async def _detect_and_store_trajectory(
    session: AsyncSession,
    person: SourcePerson,
    new_snapshot: PersonPositionSnapshot,
    prev_snapshot: Optional[PersonPositionSnapshot],
) -> None:
    """Jämför ny snapshot med föregående och lagra eventuell förflyttning."""
    if not prev_snapshot:
        return

    dims = [
        ("political_leaning", LEANING_SCALE, "political_leaning", "political_leaning"),
        ("gal_tan",           GAL_TAN_SCALE,  "gal_tan_position",  "gal_tan_position"),
        ("economic",          LEANING_SCALE,  "economic_position",  "economic_position"),
    ]

    for dim_name, scale, attr_from, attr_to in dims:
        v_from = getattr(prev_snapshot, attr_from)
        v_to   = getattr(new_snapshot, attr_to)
        i_from = _leaning_to_int(v_from, scale)
        i_to   = _leaning_to_int(v_to, scale)

        if i_from is None or i_to is None:
            continue

        delta = i_to - i_from
        direction = _direction_from_delta(delta, dim_name)
        magnitude = _magnitude_from_delta(delta)
        significance = "major" if abs(delta) >= 3 else ("notable" if abs(delta) >= 2 else "routine")

        traj = PersonTrajectory(
            person_id=person.id,
            snapshot_from_id=prev_snapshot.id,
            snapshot_to_id=new_snapshot.id,
            period_from=prev_snapshot.period_end,
            period_to=new_snapshot.period_end,
            dimension=dim_name,
            value_from=v_from,
            value_to=v_to,
            direction=direction,
            magnitude=magnitude,
            significance=significance,
            trajectory_notes=(
                f"{person.name}: {dim_name} {v_from} → {v_to} "
                f"({magnitude}, {direction})"
            ) if magnitude != "none" else None,
        )
        session.add(traj)

    if magnitude := "notable":  # log meaningful movements
        logger.debug(f"  Trajektori beräknad för {person.name}")


# ---------------------------------------------------------------------------
# Huvud-analysfunktion
# ---------------------------------------------------------------------------

async def analyze_person(
    person: SourcePerson,
    session: AsyncSession,
    min_statements: int = 3,
    force: bool = False,
) -> Optional[dict]:
    """
    Kör Claude-analys för en persons insamlade uttalanden.

    Skapar:
      - AnalysisRun med token/kostnadsspårning
      - AnalysisStatementContribution per inkluderat uttalande (med beta-vikter)
      - PersonPositionSnapshot (tidsstämplad, auktoritativ)
      - PersonTrajectory om tidigare snapshot finns
      - Uppdaterar source_persons.revealed_* som convenience-cache

    Returnerar analysresultatet som dict, eller None om för få uttalanden.
    """
    count = await session.scalar(
        select(func.count()).where(PersonStatement.person_id == person.id)
    )
    if (count or 0) < min_statements:
        logger.info(f"  {person.name}: {count} uttalanden — för få (min {min_statements}), hoppar")
        return None

    if not force and person.revealed_updated_at:
        logger.info(f"  {person.name}: redan analyserad {person.revealed_updated_at.date()}, hoppar (--force för omanalys)")
        return None

    statements: list[PersonStatement] = (
        await session.execute(
            select(PersonStatement)
            .where(PersonStatement.person_id == person.id)
            .order_by(PersonStatement.published_at.desc())
        )
    ).scalars().all()

    # Beräkna beta-vikter
    weighted = _compute_weights(list(statements))

    # Bygg statements-block med token-gräns (högst viktade först)
    sorted_weighted = sorted(weighted, key=lambda x: x[1], reverse=True)
    chunks, included_ids, excluded_ids = [], [], []
    total_chars, limit = 0, MAX_CONTENT_TOKENS * 4

    for stmt, weight, w_rec, w_plat, w_len in sorted_weighted:
        content = (stmt.content or "").strip()
        if len(content) > MAX_CHARS_PER_STATEMENT:
            content = content[:MAX_CHARS_PER_STATEMENT] + "…"
        date_str = stmt.published_at.strftime("%Y-%m") if stmt.published_at else "?"
        chunk = f"[{stmt.platform.upper()} {date_str} w={weight:.3f}]\n{content}"

        if total_chars + len(chunk) > limit:
            excluded_ids.append(stmt.id)
            continue

        chunks.append(chunk)
        included_ids.append(stmt.id)
        total_chars += len(chunk)

    statements_block = "\n\n---\n\n".join(chunks)
    platforms = sorted(set(s.platform for s, *_ in sorted_weighted))

    # Tidsspann
    dates = [s.published_at for s, *_ in sorted_weighted if s.published_at]
    period_start = min(dates).date() if dates else None
    period_end   = max(dates).date() if dates else None
    period_str   = f"{period_start} – {period_end}" if period_start else "okänt"

    prompt = _PROMPT_TEMPLATE.format(
        name=person.name,
        title=person.title or "okänd roll",
        declared_leaning=person.political_leaning or "okänd",
        declared_gal_tan=person.gal_tan_position or "okänd",
        declared_economic=person.economic_position or "okänd",
        party=person.party_affiliation or "inget parti",
        n_statements=len(included_ids),
        platforms=", ".join(platforms),
        period=period_str,
        statements_block=statements_block,
    )

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY saknas")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    logger.info(f"  {person.name}: {len(included_ids)} uttalanden → Claude ({ANALYSIS_MODEL})")

    try:
        message = await client.messages.create(
            model=ANALYSIS_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error(f"  Claude API-fel för {person.name}: {e}")
        return None

    raw = message.content[0].text.strip()
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        if m:
            raw = m.group(1)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"  JSON-fel för {person.name}: {e}\nRå: {raw[:300]}")
        return None

    # API-kostnadsberäkning (Haiku-4-5 priser per april 2025)
    t_in  = message.usage.input_tokens
    t_out = message.usage.output_tokens
    cost_usd = (t_in * 0.80 + t_out * 4.0) / 1_000_000  # $0.80/$4.00 per MTok

    # --- Skapa AnalysisRun ---
    run = AnalysisRun(
        person_id=person.id,
        model_used=ANALYSIS_MODEL,
        source_platforms=platforms,
        statements_analyzed=len(included_ids),
        tokens_input=t_in,
        tokens_output=t_out,
        cost_usd=cost_usd,
        period_start=period_start,
        period_end=period_end,
        status="completed",
    )
    session.add(run)
    await session.flush()  # får run.id

    # --- Skapa AnalysisStatementContributions ---
    stmt_map = {s.id: (s, w, wr, wp, wl) for s, w, wr, wp, wl in sorted_weighted}
    for sid in included_ids + excluded_ids:
        if sid not in stmt_map:
            continue
        _, w, wr, wp, wl = stmt_map[sid]
        contrib = AnalysisStatementContribution(
            analysis_run_id=run.id,
            statement_id=sid,
            weight=w,
            weight_recency=wr,
            weight_platform=wp,
            weight_length=wl,
            included=(sid in included_ids),
        )
        session.add(contrib)

    # --- Hämta föregående snapshot (för trajektoridetektering) ---
    prev_snapshot: Optional[PersonPositionSnapshot] = await session.scalar(
        select(PersonPositionSnapshot)
        .where(PersonPositionSnapshot.person_id == person.id, PersonPositionSnapshot.is_current == True)
        .order_by(PersonPositionSnapshot.created_at.desc())
    )

    # Avmarkera gamla "is_current"
    if prev_snapshot:
        await session.execute(
            update(PersonPositionSnapshot)
            .where(PersonPositionSnapshot.person_id == person.id)
            .values(is_current=False)
        )

    # --- Skapa PersonPositionSnapshot ---
    snapshot = PersonPositionSnapshot(
        person_id=person.id,
        analysis_run_id=run.id,
        period_start=period_start,
        period_end=period_end,
        political_leaning=result.get("revealed_political_leaning"),
        gal_tan_position=result.get("revealed_gal_tan_position"),
        economic_position=result.get("revealed_economic_position"),
        confidence=result.get("confidence"),
        vs_declared_discrepancy=result.get("discrepancy"),
        key_themes=result.get("key_themes", []),
        analysis_notes=result.get("analysis_notes"),
        source_platforms=platforms,
        statements_count=len(included_ids),
        is_current=True,
    )
    session.add(snapshot)
    await session.flush()  # får snapshot.id

    # --- Detektera och lagra trajektori ---
    await _detect_and_store_trajectory(session, person, snapshot, prev_snapshot)

    # --- Uppdatera source_persons.revealed_* (convenience-cache) ---
    await session.execute(
        update(SourcePerson)
        .where(SourcePerson.id == person.id)
        .values(
            revealed_political_leaning=result.get("revealed_political_leaning"),
            revealed_gal_tan_position=result.get("revealed_gal_tan_position"),
            revealed_economic_position=result.get("revealed_economic_position"),
            revealed_confidence=result.get("confidence"),
            revealed_updated_at=datetime.now(tz=timezone.utc),
            leaning_discrepancy=result.get("discrepancy"),
            statements_count=len(included_ids),
            classification_notes=(
                (person.classification_notes or "") +
                f"\n[Revealed {datetime.now().strftime('%Y-%m-%d')}]: {result.get('analysis_notes', '')}"
            ).strip(),
        )
    )

    await session.commit()

    logger.info(
        f"  {person.name}: revealed={result.get('revealed_political_leaning')} "
        f"(declared={person.political_leaning}), "
        f"discrepancy={result.get('discrepancy')}, "
        f"conf={result.get('confidence', 0):.2f}, "
        f"cost=${cost_usd:.4f}"
    )

    return result


async def analyze_all_persons(
    session: AsyncSession,
    min_statements: int = 3,
    force: bool = False,
) -> dict[str, Optional[dict]]:
    """Analysera alla personer i DB med tillräckligt många uttalanden."""
    persons = (await session.execute(select(SourcePerson))).scalars().all()
    logger.info(f"Analyserar {len(persons)} personer...")

    results = {}
    for person in persons:
        result = await analyze_person(person, session, min_statements=min_statements, force=force)
        results[person.name] = result

    return results
