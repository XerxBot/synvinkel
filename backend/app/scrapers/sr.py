"""
SR-scraper — Sveriges Radio Open API v2.
Hämtar nyheter från Ekot och Studio ett.
API-dokumentation: https://sverigesradio.se/artikel/api-dokumentation

SR returnerar datum som .NET JSON-datum: /Date(milliseconds+offset)/
"""
import logging
import re
from datetime import datetime, timezone

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

_SR_NEWS_API = "https://api.sr.se/api/v2/news"

# Program-IDs: Ekot (riksnyheter) + Studio ett (samhällsdebatt P1)
_SR_PROGRAMS = [
    (83,  "Ekot"),
    (163, "Studio ett"),
]


def _parse_sr_date(raw: str) -> datetime | None:
    """/Date(milliseconds+offset)/ → datetime (UTC). Fallback: ISO 8601."""
    if not raw:
        return None
    m = re.search(r"/Date\((-?\d+)", raw)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class SRScraper(BaseScraper):
    source_slug = "sr-ekot"
    base_url = "https://sverigesradio.se"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []
        seen_urls: set[str] = set()
        per_program = max(10, limit // len(_SR_PROGRAMS) + 5)

        for program_id, program_name in _SR_PROGRAMS:
            if len(articles) >= limit:
                break
            try:
                resp = await self._get(
                    _SR_NEWS_API,
                    params={
                        "format": "json",
                        "programid": program_id,
                        "size": per_program,
                        "page": 1,
                        "pagination": "false",
                    },
                )
                data = resp.json()
            except Exception as e:
                logger.error("SR API misslyckades (program %d %s): %s", program_id, program_name, e)
                continue

            for item in data.get("news", []):
                url: str = item.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title: str = item.get("title", "").strip()
                if not title:
                    continue

                articles.append(
                    ScrapedArticle(
                        url=url,
                        title=title,
                        source_slug=self.source_slug,
                        full_text=item.get("description") or None,
                        published_at=_parse_sr_date(item.get("publishedatutc", "")),
                        article_type="nyhet",
                        section=program_name,
                        language="sv",
                    )
                )
                if len(articles) >= limit:
                    break

        logger.info("SR: %d artiklar hämtade", len(articles))
        return articles
