"""
SR-scraper — Sveriges Radio Open API v2.
Använder episodes/index-endpointen med program-IDs för nyhetssändningar.

OBS: SR är audio-first. Episodsidor har ingen extraherbar fulltext.
Scrapern hämtar titlar (faktiska nyhetsrubriker) + beskrivningar.
NLP-analys baseras på rubrik + ev. episodbeskrivning.

Program-IDs:
  4540 — Ekot nyhetssändning (rubriker är verkliga nyhetsrubriker)
  3437 — Ekot granskar (granskande journalistik)
  5251 — Ekots fördjupningar
  1637 — Studio ett (samhällsdebatt P1)
"""
import logging
import re
from datetime import datetime, timezone

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

_SR_EPISODES_API = "https://api.sr.se/api/v2/episodes/index"

# Program-IDs och sektionsnamn — prioritetsordning
_SR_PROGRAMS = [
    (4540, "Ekot nyhetssändning"),
    (3437, "Ekot granskar"),
    (5251, "Ekots fördjupningar"),
    (1637, "Studio ett"),
]


def _parse_sr_date(raw: str) -> datetime | None:
    """/Date(milliseconds+offset)/ → datetime (UTC)."""
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

        for program_id, section in _SR_PROGRAMS:
            if len(articles) >= limit:
                break
            try:
                resp = await self._get(
                    _SR_EPISODES_API,
                    params={
                        "format": "json",
                        "programid": program_id,
                        "size": per_program,
                        "pagination": "false",
                    },
                )
                episodes = resp.json().get("episodes", [])
            except Exception as e:
                logger.error("SR episodes API misslyckades (program %d %s): %s", program_id, section, e)
                continue

            for ep in episodes:
                url: str = ep.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title: str = ep.get("title", "").strip()
                if not title:
                    continue

                # Rensa bort generiska programbeskrivningar som inte är nyhetsspecifika
                description: str = ep.get("description", "").strip()
                # Om beskrivningen är identisk med programnamnet är den generisk
                is_generic = description.lower() in (
                    section.lower(),
                    "ekots dagliga, längre sändningar med nyheter och fördjupning.",
                    "direktsänt aktuellt magasin.",
                    "senaste nytt från ekot – varje timme.",
                )
                full_text = None if is_generic else description

                articles.append(
                    ScrapedArticle(
                        url=url,
                        title=title,
                        source_slug=self.source_slug,
                        full_text=full_text,
                        published_at=_parse_sr_date(ep.get("publishdateutc", "")),
                        article_type="nyhet",
                        section=section,
                        language="sv",
                    )
                )
                if len(articles) >= limit:
                    break

        logger.info("SR: %d artiklar hämtade", len(articles))
        return articles
