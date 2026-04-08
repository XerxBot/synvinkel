"""
Scraper för Riksdagens öppna data API.
API-dokumentation: https://data.riksdagen.se
"""
import logging

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

RIKSDAGEN_API = "https://data.riksdagen.se"


class RiksdagenScraper(BaseScraper):
    source_slug = "riksdagen"
    base_url = RIKSDAGEN_API

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        """Hämta senaste anföranden från riksdagens API."""
        articles: list[ScrapedArticle] = []
        try:
            url = f"{RIKSDAGEN_API}/anforandelista/?anftyp=Nej&utformat=json&antal={limit}&sort=d"
            resp = await self._get(url)
            data = resp.json()
            anforanden = data.get("anforandelista", {}).get("anforande", [])

            for a in anforanden[:limit]:
                anf_id = a.get("anforande_id", "")
                anf_url = f"https://www.riksdagen.se/sv/dokument-och-lagar/dokument/anforande/{anf_id}/"
                talare = a.get("talare", "")
                rubrik = a.get("avsnittsrubrik") or a.get("kammaraktivitet") or "Anförande"

                articles.append(
                    ScrapedArticle(
                        url=anf_url,
                        title=f"{talare}: {rubrik}".strip(": "),
                        source_slug=self.source_slug,
                        full_text=a.get("anforandetext"),
                        article_type="anforande",
                        section=a.get("kammaraktivitet"),
                        author_names=[talare] if talare else [],
                    )
                )

        except Exception as e:
            logger.error(f"Riksdagen scrape misslyckades: {e}")

        logger.info(f"Riksdagen: {len(articles)} anföranden hämtade")
        return articles

    async def fetch_motioner(self, limit: int = 20, session: str = "2024/25") -> list[ScrapedArticle]:
        """Hämta motioner från riksdagen."""
        articles: list[ScrapedArticle] = []
        try:
            url = f"{RIKSDAGEN_API}/dokumentlista/?doktyp=mot&rm={session}&utformat=json&antal={limit}&sort=d"
            resp = await self._get(url)
            data = resp.json()
            dokument = data.get("dokumentlista", {}).get("dokument", [])

            for d in dokument[:limit]:
                dok_url = d.get("dokumentstatus_url_xml", "").replace("_status.xml", "")
                if not dok_url:
                    dok_url = f"https://riksdagen.se/sv/dokument-och-lagar/{d.get('id', '')}"

                articles.append(
                    ScrapedArticle(
                        url=dok_url,
                        title=d.get("titel", "Motion"),
                        source_slug=self.source_slug,
                        subtitle=d.get("subtitel"),
                        article_type="motion",
                        section=d.get("organ"),
                        author_names=[d.get("organ", "")] if d.get("organ") else [],
                    )
                )

        except Exception as e:
            logger.error(f"Riksdagen motioner misslyckades: {e}")

        return articles
