"""
ArticleIngestor — scrape → NLP → DB i en transaktion.
Deduplicerar på URL. Skapar ArticleAnalysis i samma commit.
"""
import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article, ArticleAnalysis
from app.models.organization import SourceOrganization
from app.scrapers.base import ScrapedArticle
from app.services.nlp import enrich

logger = logging.getLogger(__name__)


class ArticleIngestor:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_org(self, source_slug: str) -> Optional[SourceOrganization]:
        return await self.db.scalar(
            select(SourceOrganization).where(SourceOrganization.slug == source_slug)
        )

    async def _url_exists(self, url: str) -> bool:
        return await self.db.scalar(select(Article.id).where(Article.url == url)) is not None

    async def _fetch_full_text(self, url: str) -> Optional[str]:
        """Hämtar och extraherar fulltext via trafilatura (körs i executor)."""
        try:
            import trafilatura

            def _download_and_extract() -> Optional[str]:
                html = trafilatura.fetch_url(url)
                if not html:
                    return None
                return trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=False,
                    favor_precision=True,
                )

            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _download_and_extract),
                timeout=15.0,
            )
            return result or None
        except Exception as e:
            logger.debug("trafilatura misslyckades för %s: %s", url, e)
            return None

    async def ingest_one(
        self,
        scraped: ScrapedArticle,
        job_id: Optional[uuid.UUID] = None,
        fetch_full_text: bool = True,
    ) -> tuple[Optional[Article], bool]:
        """
        Persistera en artikel. Returnerar (article, is_new).
        is_new=False → URL-dubblett, returnerar None.
        """
        if not scraped.url:
            return None, False

        if await self._url_exists(scraped.url):
            return None, False

        # Hämta fulltext om scrapern inte levererade den
        if not scraped.full_text and fetch_full_text:
            scraped.full_text = await self._fetch_full_text(scraped.url)

        # NLP-enrichment (spaCy NER + keyword topics + partidetektering)
        text = scraped.full_text or scraped.title or ""
        nlp = enrich(text)

        # Slå upp source org
        org = await self._get_org(scraped.source_slug) if scraped.source_slug else None

        article = Article(
            url=scraped.url,
            title=scraped.title,
            subtitle=scraped.subtitle,
            full_text=scraped.full_text,
            published_at=scraped.published_at,
            source_org_id=org.id if org else None,
            author_names=scraped.author_names or [],
            article_type=scraped.article_type,
            section=scraped.section,
            language=scraped.language,
            word_count=nlp.word_count or None,
            topics=nlp.topics or [],
            mentioned_parties=nlp.mentioned_parties or [],
            mentioned_persons=nlp.mentioned_persons or [],
            mentioned_orgs=nlp.mentioned_orgs or [],
            sentiment_score=nlp.sentiment_score,
            data_source=scraped.source_slug,
            scrape_job_id=job_id,
        )
        self.db.add(article)
        # flush → article.id finns, kan refereras av ArticleAnalysis
        await self.db.flush()

        # Avvikelsedetektering — jämför innehåll mot avsändarprofil
        deviation_data: dict | None = None
        if org:
            from app.services.deviation import compute_deviation
            deviation_data = compute_deviation(nlp, org)

        # Skapa ArticleAnalysis med avsändarmetadata + avvikelseflaggor
        analysis = ArticleAnalysis(
            article_id=article.id,
            source_political_leaning=org.political_leaning if org else None,
            source_funding_category=org.funding_category if org else None,
            source_type=org.type if org else None,
            analysis_version="v0.1",
            confidence_score=deviation_data["deviation_score"] if deviation_data else None,
            confidence_explanation=", ".join(deviation_data["flags"]) if deviation_data and deviation_data["flags"] else None,
            coverage_spectrum=deviation_data,
        )
        self.db.add(analysis)

        return article, True

    async def ingest_batch(
        self,
        articles: list[ScrapedArticle],
        job_id: Optional[uuid.UUID] = None,
        fetch_full_text: bool = True,
    ) -> tuple[int, int]:
        """
        Ingest en batch. Returnerar (found, new).
        En commit per batch för effektivitet.
        """
        found = len(articles)
        new_count = 0

        for scraped in articles:
            try:
                _, is_new = await self.ingest_one(
                    scraped, job_id=job_id, fetch_full_text=fetch_full_text
                )
                if is_new:
                    new_count += 1
            except Exception as e:
                logger.error("Ingest-fel för %s: %s", scraped.url, e)
                await self.db.rollback()
                # SQLAlchemy 2.0 async session startar ny transaktion automatiskt

        await self.db.commit()
        logger.info("Ingest klar: %d hittade, %d nya", found, new_count)
        return found, new_count
