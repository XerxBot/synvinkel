"""
KorpScraper — hämtar SVT-nyhetsartiklar via Språkbanken Korp API v8.
Dokumentation: https://ws.spraakbanken.gu.se/ws/korp/v8
"""
import logging
from datetime import datetime
from typing import Optional

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

KORP_BASE_URL = "https://ws.spraakbanken.gu.se/ws/korp/v8"


class KorpScraper(BaseScraper):
    source_slug = "svt-nyheter"
    base_url = KORP_BASE_URL

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        """Hämtar SVT-artiklar från Korp-konkordanssökning."""
        try:
            corpora = await self._get_svt_corpora()
            if not corpora:
                logger.warning("Inga SVT-korpusar hittades i Korp")
                return []

            recent_corpora = corpora[:3]
            corpus_param = ",".join(recent_corpora)
            logger.info("Söker i korpusar: %s", corpus_param)

            url = (
                f"{KORP_BASE_URL}/concordance"
                f"?corpus={corpus_param}"
                f"&cqp=[word+!%3D+%22.%22]{{10,}}"
                f"&start=0"
                f"&end={limit - 1}"
                f"&show_struct=text_title,text_date,text_url"
                f"&within=text"
            )

            response = await self._get(url)
            data = response.json()

            kwic = data.get("kwic", [])
            if not kwic:
                logger.info("Korp returnerade inga träffar")
                return []

            seen_urls: set[str] = set()
            articles: list[ScrapedArticle] = []

            for hit in kwic:
                structs = hit.get("structs", {})
                text_url: Optional[str] = structs.get("text_url")

                if not text_url:
                    continue

                if text_url in seen_urls:
                    continue
                seen_urls.add(text_url)

                title: str = structs.get("text_title") or "SVT-artikel"

                published_at: Optional[datetime] = None
                raw_date = structs.get("text_date")
                if raw_date:
                    try:
                        published_at = datetime.strptime(raw_date, "%Y%m%d")
                    except ValueError:
                        logger.debug("Kunde inte tolka datum: %s", raw_date)

                tokens = hit.get("tokens", [])
                full_text: str = " ".join(t["word"] for t in tokens if "word" in t)

                articles.append(
                    ScrapedArticle(
                        url=text_url,
                        title=title,
                        source_slug=self.source_slug,
                        full_text=full_text or None,
                        published_at=published_at,
                        article_type="nyhetsartikel",
                        language="sv",
                    )
                )

                if len(articles) >= limit:
                    break

            logger.info("KorpScraper hämtade %d unika artiklar", len(articles))
            return articles

        except Exception:
            logger.exception("KorpScraper misslyckades")
            return []

    async def _get_svt_corpora(self) -> list[str]:
        """Hämtar alla Korp-korpusar och returnerar SVT-korpusar sorterade fallande."""
        try:
            response = await self._get(f"{KORP_BASE_URL}/corpora")
            data = response.json()
            all_corpora: list[str] = data.get("corpora", [])
            svt_corpora = [c for c in all_corpora if c.upper().startswith("SVT")]
            svt_corpora.sort(reverse=True)
            return svt_corpora
        except Exception:
            logger.exception("Kunde inte hämta korpuslista från Korp")
            return []
