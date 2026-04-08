"""Scraper för Timbro — marknadsliberal tankesmedja."""
import logging

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

REPORTS_URL = "https://timbro.se/content_type/rapporter/"


class TimbróScraper(BaseScraper):
    source_slug = "timbro"
    base_url = "https://timbro.se"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []
        try:
            resp = await self._get(REPORTS_URL)
            soup = BeautifulSoup(resp.text, "lxml")

            # Timbro uses article cards — selector may need updating if layout changes
            items = soup.select("article, .entry-item, .publication-card")[:limit]

            for item in items:
                link = item.find("a", href=True)
                title_el = item.find(["h2", "h3", "h4"])
                if not link or not title_el:
                    continue

                url: str = link["href"]
                if not url.startswith("http"):
                    url = self.base_url + url

                articles.append(
                    ScrapedArticle(
                        url=url,
                        title=title_el.get_text(strip=True),
                        source_slug=self.source_slug,
                        article_type="rapport",
                        section="rapporter",
                    )
                )

        except Exception as e:
            logger.error(f"Timbro scrape misslyckades: {e}")

        logger.info(f"Timbro: {len(articles)} artiklar hämtade")
        return articles
