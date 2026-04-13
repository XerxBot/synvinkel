"""
Analyserar insamlade uttalanden med Claude (Haiku) och bygger en 'revealed position'
per person — dvs vad de faktiskt säger snarare än vad deras partibok eller institution säger.

Kostnad: ~0.1–0.5 SEK per person (Claude Haiku-4-5 priser per april 2025).
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import anthropic
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organization import SourcePerson
from app.models.statement import PersonStatement

logger = logging.getLogger(__name__)

# Haiku är billig och snabb — räcker väl för denna klassificering
ANALYSIS_MODEL = "claude-haiku-4-5-20251001"

# Max tokens att skicka som uttalanden (håll kostnaden nere)
MAX_CONTENT_TOKENS = 12_000   # ~9 000 ord
MAX_CHARS_PER_STATEMENT = 800  # trunkera långa anföranden


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

INSAMLADE UTTALANDEN ({n_statements} st, plattformar: {platforms}):
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
  "analysis_notes": "2-4 meningar som förklarar den faktiska positionen och eventuella avvikelser från institutionell profil"
}}

Definitioner för discrepancy:
- none: faktisk position stämmer med institutionell
- minor: liten avvikelse i nyans eller ton
- moderate: tydlig skillnad på en axel (t.ex. ekonomiskt mer vänster än partiet)
- significant: faktisk position skiljer sig markant från institutionell (Carl Bildt-fallet)"""


def _build_statements_block(statements: list[PersonStatement]) -> tuple[str, list[str]]:
    """
    Bygg en komprimerad textsträng av uttalanden att skicka till Claude.
    Returnerar (text, lista_av_plattformar).
    """
    platforms = sorted(set(s.platform for s in statements))
    chunks = []
    total_chars = 0
    limit = MAX_CONTENT_TOKENS * 4  # ungefärlig konvertering tokens → chars

    for s in sorted(statements, key=lambda x: x.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        content = (s.content or "").strip()
        if len(content) > MAX_CHARS_PER_STATEMENT:
            content = content[:MAX_CHARS_PER_STATEMENT] + "…"

        date_str = s.published_at.strftime("%Y-%m") if s.published_at else "okänt datum"
        platform_label = s.platform.upper()
        chunk = f"[{platform_label} {date_str}]\n{content}"

        if total_chars + len(chunk) > limit:
            break

        chunks.append(chunk)
        total_chars += len(chunk)

    return "\n\n---\n\n".join(chunks), platforms


async def analyze_person(
    person: SourcePerson,
    session: AsyncSession,
    min_statements: int = 3,
    force: bool = False,
) -> Optional[dict]:
    """
    Kör Claude-analys för en persons insamlade uttalanden.
    Uppdaterar revealed_* fält på personen i DB.
    Returnerar analysresultatet som dict, eller None om för få uttalanden.
    """
    # Räkna statements
    count = await session.scalar(
        select(func.count()).where(PersonStatement.person_id == person.id)
    )
    if (count or 0) < min_statements:
        logger.info(f"  {person.name}: {count} uttalanden — för få (min {min_statements}), hoppar")
        return None

    if not force and person.revealed_updated_at:
        logger.info(f"  {person.name}: redan analyserad {person.revealed_updated_at.date()}, hoppar (--force för omanalys)")
        return None

    statements = (
        await session.execute(
            select(PersonStatement)
            .where(PersonStatement.person_id == person.id)
            .order_by(PersonStatement.published_at.desc())
        )
    ).scalars().all()

    statements_block, platforms = _build_statements_block(list(statements))

    prompt = _PROMPT_TEMPLATE.format(
        name=person.name,
        title=person.title or "okänd roll",
        declared_leaning=person.political_leaning or "okänd",
        declared_gal_tan=person.gal_tan_position or "okänd",
        declared_economic=person.economic_position or "okänd",
        party=person.party_affiliation or "inget parti",
        n_statements=len(statements),
        platforms=", ".join(platforms),
        statements_block=statements_block,
    )

    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY saknas")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info(f"  {person.name}: skickar {len(statements)} uttalanden till Claude ({ANALYSIS_MODEL})")

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

    # Rensa markdown-kodblock om Claude lade till dem
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        if m:
            raw = m.group(1)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"  JSON-fel för {person.name}: {e}\nRå: {raw[:300]}")
        return None

    # Uppdatera personen i DB
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
            statements_count=len(statements),
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
        f"confidence={result.get('confidence', 0):.2f}"
    )

    return result


async def analyze_all_persons(
    session: AsyncSession,
    min_statements: int = 3,
    force: bool = False,
) -> dict[str, Optional[dict]]:
    """
    Analysera alla personer i DB med tillräckligt många uttalanden.
    Returnerar {person_name: result_dict}.
    """
    persons = (await session.execute(select(SourcePerson))).scalars().all()
    logger.info(f"Analyserar {len(persons)} personer...")

    results = {}
    for person in persons:
        result = await analyze_person(person, session, min_statements=min_statements, force=force)
        results[person.name] = result

    return results
