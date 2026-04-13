"""
Kör Claude-analys på insamlade uttalanden och bygger 'revealed position' per person.

Kör med:
    docker compose exec backend python -m app.analyze_persons
    docker compose exec backend python -m app.analyze_persons --person "Carl Bildt"
    docker compose exec backend python -m app.analyze_persons --force   # omanalysera alla
    docker compose exec backend python -m app.analyze_persons --min-statements 5

Förutsättning: kör collect_statements.py först för att samla in uttalanden.

Kostnad (Claude Haiku-4-5, april 2025):
    Input:  $0.25 / 1M tokens
    Output: $1.25 / 1M tokens
    Per person (~10 000 input-tokens): ~$0.0025 ≈ 0.026 SEK
    Alla 79 personer: ~$0.20 ≈ 2 SEK
"""
import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models.organization import SourcePerson

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main(
    person_filter: str | None,
    min_statements: int,
    force: bool,
):
    from app.analysis.statement_analyzer import analyze_person

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as session:
        query = select(SourcePerson)
        if person_filter:
            query = query.where(SourcePerson.name.ilike(f"%{person_filter}%"))

        persons = (await session.execute(query)).scalars().all()
        logger.info(f"Analyserar {len(persons)} person(er)...")

        analyzed = 0
        skipped = 0
        discrepancies = []

        for person in persons:
            logger.info(f"\n{person.name}")
            result = await analyze_person(
                person, session,
                min_statements=min_statements,
                force=force,
            )
            if result:
                analyzed += 1
                if result.get("discrepancy") in ("moderate", "significant"):
                    discrepancies.append({
                        "name": person.name,
                        "declared": person.political_leaning,
                        "revealed": result.get("revealed_political_leaning"),
                        "discrepancy": result.get("discrepancy"),
                        "notes": result.get("analysis_notes", "")[:120],
                    })
            else:
                skipped += 1

        logger.info("\n=== Summering ===")
        logger.info(f"  Analyserade: {analyzed}")
        logger.info(f"  Hoppade över: {skipped}")

        if discrepancies:
            logger.info(f"\n=== Avvikelser (moderate/significant) ===")
            for d in discrepancies:
                logger.info(
                    f"  {d['name']}: {d['declared']} → {d['revealed']} [{d['discrepancy']}]"
                    f"\n    {d['notes']}"
                )

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analysera politisk position från uttalanden")
    parser.add_argument("--person", default=None, help="Filtrera på personnamn")
    parser.add_argument("--min-statements", type=int, default=3, help="Min antal uttalanden för analys")
    parser.add_argument("--force", action="store_true", help="Omanalysera även redan analyserade")
    args = parser.parse_args()

    asyncio.run(main(
        person_filter=args.person,
        min_statements=args.min_statements,
        force=args.force,
    ))
