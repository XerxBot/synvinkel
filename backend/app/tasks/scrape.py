"""
Scraping-jobb — körs via FastAPI BackgroundTasks.
Varje jobb: scraper → ArticleIngestor → uppdatera ScrapeJob-status.
Uppgraderas till ARQ (Redis queue) i Fas 2 för reliabilitet.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.models.article import ScrapeJob

logger = logging.getLogger(__name__)

# Registry: source_slug → scraper-klass (lazy import inuti funktionen)
SCRAPER_REGISTRY: dict[str, str] = {
    "timbro":             "app.scrapers.timbro:TimbróScraper",
    "katalys":            "app.scrapers.katalys:KatalysScraper",
    "arena-ide":          "app.scrapers.arenaide:ArenaIdéScraper",
    "riksdagen":          "app.scrapers.riksdagen:RiksdagenScraper",
    "riksdagen-motioner": "app.scrapers.riksdagen:RiksdagenScraper",
    "svt-nyheter":           "app.scrapers.svt:SVTScraper",
    "sr-ekot":               "app.scrapers.sr:SRScraper",
    "reddit-svenska":        "app.scrapers.reddit:RedditScraper",
    "nmi":                   "app.scrapers.nmi:NMIScraper",
    "svenskt-naringsliv":    "app.scrapers.svensktnaringsliv:SvensktNaringlivScraper",
}


def _load_scraper(path: str):
    """Lazy-importera scraper-klass från 'module:ClassName'-sträng."""
    module_path, class_name = path.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


async def run_scrape_job(
    job_id: uuid.UUID,
    source_slug: str,
    limit: int = 20,
) -> None:
    """
    Körs som BackgroundTask — öppnar egna DB-sessioner (ej request-scopade).
    ScrapeJob.status: queued → running → completed / failed
    """
    # Markera som running
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()

    articles_found = 0
    articles_new = 0
    errors: dict = {}

    try:
        scraper_path = SCRAPER_REGISTRY.get(source_slug)
        if not scraper_path:
            raise ValueError(
                f"Okänd source_slug '{source_slug}'. "
                f"Tillgängliga: {list(SCRAPER_REGISTRY)}"
            )

        scraper_class = _load_scraper(scraper_path)

        async with scraper_class() as scraper:
            if source_slug == "riksdagen-motioner":
                raw = await scraper.fetch_motioner(limit=limit)
            else:
                raw = await scraper.fetch_articles(limit=limit)

        articles_found = len(raw)

        # Ingest i separat session
        from app.services.ingestor import ArticleIngestor
        async with AsyncSessionLocal() as db:
            ingestor = ArticleIngestor(db)
            _, articles_new = await ingestor.ingest_batch(raw, job_id=job_id)

        status = "completed"

    except Exception as e:
        logger.exception("Scrape-jobb %s misslyckades: %s", job_id, e)
        errors["fatal"] = str(e)
        status = "failed"

    # Uppdatera slutstatus
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ScrapeJob)
            .where(ScrapeJob.id == job_id)
            .values(
                status=status,
                completed_at=datetime.now(timezone.utc),
                articles_found=articles_found,
                articles_new=articles_new,
                errors=errors if errors else None,
            )
        )
        await db.commit()

    logger.info(
        "Jobb %s klar: status=%s, hittade=%d, nya=%d",
        job_id, status, articles_found, articles_new,
    )
