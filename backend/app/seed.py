"""
Ladda seed-data (organisationer, ämnen, skribenter) i databasen.

Kör med:
    docker compose exec backend python -m app.seed
    # eller lokalt:
    uv run python -m app.seed
"""
import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent.parent / "data" / "seed"


async def seed_organizations(session: AsyncSession) -> int:
    from app.models.organization import SourceOrganization

    path = SEED_DIR / "organizations.json"
    orgs = json.loads(path.read_text(encoding="utf-8"))
    created = 0

    for org_data in orgs:
        existing = await session.scalar(
            select(SourceOrganization).where(SourceOrganization.slug == org_data["slug"])
        )
        if existing:
            continue
        session.add(SourceOrganization(**org_data))
        created += 1

    await session.commit()
    return created


async def seed_topics(session: AsyncSession) -> int:
    from app.models.topic import Topic

    path = SEED_DIR / "topics.json"
    topics = json.loads(path.read_text(encoding="utf-8"))
    created = 0

    for topic_data in topics:
        existing = await session.scalar(
            select(Topic).where(Topic.slug == topic_data["slug"])
        )
        if existing:
            continue
        session.add(Topic(**topic_data))
        created += 1

    await session.commit()
    return created


async def seed_persons(session: AsyncSession) -> tuple[int, int]:
    """Upsert-baserad seed — skapar nya och uppdaterar befintliga."""
    from app.models.organization import SourceOrganization, SourcePerson

    path = SEED_DIR / "persons.json"
    persons = json.loads(path.read_text(encoding="utf-8"))

    # Bygg org_slug → id-mappning
    org_rows = (await session.execute(select(SourceOrganization))).scalars().all()
    org_map = {org.slug: org.id for org in org_rows}

    created = 0
    updated = 0

    for p in persons:
        org_slug = p.pop("org_slug", None)
        org_id = org_map.get(org_slug) if org_slug else None
        if org_slug and not org_id:
            logger.warning(f"  Okänd org_slug '{org_slug}' för {p['name']} — hoppar över org-länk")

        # Lös secondary_org_slugs → secondary_org_ids (lista av UUIDs)
        secondary_slugs = p.pop("secondary_org_slugs", None) or []
        secondary_ids = []
        for s_slug in secondary_slugs:
            s_id = org_map.get(s_slug)
            if s_id:
                secondary_ids.append(s_id)
            else:
                logger.warning(f"  Okänd secondary_org_slug '{s_slug}' för {p['name']} — ignoreras")

        values = {**p, "organization_id": org_id, "secondary_org_ids": secondary_ids or None}

        # Kontrollera om personen finns (för loggning)
        existing = await session.scalar(
            select(SourcePerson).where(SourcePerson.slug == p["slug"])
        )

        # Upsert: INSERT ... ON CONFLICT (slug) DO UPDATE
        stmt = pg_insert(SourcePerson).values(**values)
        update_cols = {
            col: stmt.excluded[col]
            for col in values
            if col not in ("id", "slug", "created_at")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["slug"],
            set_=update_cols,
        )
        await session.execute(stmt)

        if existing:
            updated += 1
        else:
            created += 1

    await session.commit()
    return created, updated


async def main():
    logger.info("Startar seed...")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as session:
        orgs = await seed_organizations(session)
        logger.info(f"  Organisationer: {orgs} nya skapade")

        topics = await seed_topics(session)
        logger.info(f"  Ämnen: {topics} nya skapade")

        created, updated = await seed_persons(session)
        logger.info(f"  Skribenter/personer: {created} nya, {updated} uppdaterade")

    await engine.dispose()
    logger.info("Seed klar. Öppna http://localhost:8000/docs för att testa.")


if __name__ == "__main__":
    asyncio.run(main())
