"""Scraper för Arena Idé — progressiv tankesmedja nära LO och S."""
import logging

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

# Prova i ordning tills en ger resultat
CANDIDATE_URLS = [
    "https://arenaide.se/publikationstyp/rapporter/",
    "https://arenaide.se/publikationer/",
    "https://arenaide.se/rapporter/",
]


class ArenaIdéScraper(BaseScraper):
    source_slug = "arena-ide"
    base_url = "https://arenaide.se"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []

        for url in CANDIDATE_URLS:
            try:
                resp = await self._get(url)
                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select(
                    "article, .post, .publication-item, .report-item, .entry"
                )[:limit]

                for item in items:
                    link = item.find("a", href=True)
                    title_el = item.find(["h2", "h3", "h4"])
                    if not link or not title_el:
                        continue

                    href: str = link["href"]
                    if not href.startswith("http"):
                        href = self.base_url + href

                    articles.append(
                        ScrapedArticle(
                            url=href,
                            title=title_el.get_text(strip=True),
                            source_slug=self.source_slug,
                            article_type="rapport",
                            section="rapporter",
                        )
                    )

                if articles:
                    break  # hittade resultat — skippa fallback-URLs

            except Exception as e:
                logger.warning("Arena Idé misslyckades för %s: %s", url, e)

        logger.info("Arena Idé: %d artiklar hämtade", len(articles))
        return articles
