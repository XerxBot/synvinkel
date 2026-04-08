"""
Ladda seed-data (37 organisationer + 13 ämnen) i databasen.

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


async def main():
    logger.info("Startar seed...")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as session:
        orgs = await seed_organizations(session)
        logger.info(f"  Organisationer: {orgs} nya skapade")

        topics = await seed_topics(session)
        logger.info(f"  Ämnen: {topics} nya skapade")

    await engine.dispose()
    logger.info("Seed klar. Öppna http://localhost:8000/docs för att testa.")


if __name__ == "__main__":
    asyncio.run(main())
