"""Scraper för Katalys — facklig, progressiv tankesmedja."""
import logging

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

REPORTS_URL = "https://katalys.org/publikationstyp/rapporter/"


class KatalysScraper(BaseScraper):
    source_slug = "katalys"
    base_url = "https://katalys.org"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []
        try:
            resp = await self._get(REPORTS_URL)
            soup = BeautifulSoup(resp.text, "lxml")

            items = soup.select("article, .publication-item, .report-card")[:limit]

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
            logger.error(f"Katalys scrape misslyckades: {e}")

        logger.info(f"Katalys: {len(articles)} artiklar hämtade")
        return articles
