"""
Samla uttalanden från alla konfigurerade källor för alla personer i DB.

Kör med:
    docker compose exec backend python -m app.collect_statements
    docker compose exec backend python -m app.collect_statements --source riksdag
    docker compose exec backend python -m app.collect_statements --source twitter
    docker compose exec backend python -m app.collect_statements --person "Carl Bildt"

Källor:
    riksdag       — Riksdagens öppna data API (gratis, alltid tillgängligt)
    twitter       — Twitter/X via twscrape (kräver konton eller guest mode)
    facebook      — Meta Graph API (kräver FACEBOOK_ACCESS_TOKEN)
    party_web     — Partiernas RSS-pressreleaser (gratis)
    government    — Regeringen.se tal och pressreleaser (gratis)
"""
import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.organization import SourcePerson

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def collect_for_person(
    person: SourcePerson,
    session: AsyncSession,
    sources: list[str],
) -> dict[str, int]:
    """Kör alla valda källor för en person. Returnerar {source: antal_nya}."""
    results = {}

    if "riksdag" in sources:
        from app.collectors.riksdag import collect_person_statements
        n = await collect_person_statements(person, session)
        results["riksdag"] = n
        if n:
            logger.info(f"  Riksdag: {n} nya anföranden för {person.name}")

    if "twitter" in sources:
        from app.collectors.social_web import collect_twitter_statements
        n = await collect_twitter_statements(person, session)
        results["twitter"] = n
        if n:
            logger.info(f"  Twitter: {n} nya tweets för {person.name}")

    if "facebook" in sources:
        from app.collectors.social_web import collect_facebook_statements
        n = await collect_facebook_statements(person, session)
        results["facebook"] = n
        if n:
            logger.info(f"  Facebook: {n} nya inlägg för {person.name}")

    if "party_web" in sources:
        from app.collectors.social_web import collect_party_pressreleases
        n = await collect_party_pressreleases(person, session)
        results["party_web"] = n
        if n:
            logger.info(f"  Parti-PR: {n} nya pressreleaser för {person.name}")

    if "government" in sources:
        from app.collectors.social_web import collect_government_speeches
        n = await collect_government_speeches(person, session)
        results["government"] = n
        if n:
            logger.info(f"  Regering: {n} nya tal för {person.name}")

    return results


async def main(sources: list[str], person_filter: str | None = None):
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as session:
        query = select(SourcePerson)
        if person_filter:
            query = query.where(SourcePerson.name.ilike(f"%{person_filter}%"))

        persons = (await session.execute(query)).scalars().all()
        logger.info(f"Samlar uttalanden för {len(persons)} person(er) från källorna: {', '.join(sources)}")

        total = {s: 0 for s in sources}
        for person in persons:
            logger.info(f"\n{person.name} ({person.title or 'ingen titel'})")
            counts = await collect_for_person(person, session, sources)
            for src, n in counts.items():
                total[src] = total.get(src, 0) + n

        logger.info("\n=== Summering ===")
        for src, n in total.items():
            logger.info(f"  {src}: {n} nya uttalanden")
        logger.info(f"  Totalt: {sum(total.values())} nya uttalanden")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Samla uttalanden för Synvinkel-personas")
    parser.add_argument(
        "--source",
        nargs="+",
        default=["riksdag", "party_web", "government"],
        choices=["riksdag", "twitter", "facebook", "party_web", "government", "all"],
        help="Vilka källor att använda (default: riksdag party_web government)",
    )
    parser.add_argument(
        "--person",
        default=None,
        help="Filtrera på personnamn (delsträng, case-insensitive)",
    )
    args = parser.parse_args()

    sources = args.source
    if "all" in sources:
        sources = ["riksdag", "twitter", "facebook", "party_web", "government"]

    asyncio.run(main(sources=sources, person_filter=args.person))
