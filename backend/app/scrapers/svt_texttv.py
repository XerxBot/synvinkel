"""
SVT Text-TV scraper — texttv.nu öppet API.
Text-TV innehåller redaktionellt skrivna nyhetsartiklar från SVT:s
nyhetsredaktion, uppdaterade varje timme. Inga transkriptioner,
ren redaktionell text — optimal för NLP-analys.

Flöde:
  1. Hämta indexsidor (101=inrikes, 104=utrikes, 115+= ekonomi)
     → plocka ut artikelsidnummer (106–299)
  2. Hämta varje artikelsida
  3. Använd content_plain (ingen HTML-strippning behövs)
"""
import logging
import re
from datetime import datetime, timezone

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

_TEXTTV_API = "https://texttv.nu/api/get/{page}"

# Indexsidor → sektion
_INDEX_PAGES = [
    (101, "Inrikes"),
    (102, "Inrikes"),
    (104, "Utrikes"),
    (105, "Utrikes"),
    (120, "Ekonomi"),
]

# Direkt kända artikelintervall om index saknar sidor
_ARTICLE_RANGE_FALLBACK = list(range(106, 160))

_GENERIC_TITLES = {"svt text", "text-tv", ""}


def _extract_page_nums(text: str) -> list[int]:
    """Plocka ut 3-siffriga sidnummer (106–299) ur indextext."""
    nums = re.findall(r'\b([12][0-9]{2})\b', text)
    return sorted(set(int(n) for n in nums if 106 <= int(n) <= 299))


class SVTTextTVScraper(BaseScraper):
    source_slug = "svt-nyheter"
    base_url = "https://texttv.nu"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        # Steg 1: samla artikelsidnummer från indexsidor
        article_pages: list[tuple[int, str]] = []  # (sidnummer, sektion)
        seen_page_nums: set[int] = set()

        for index_page, section in _INDEX_PAGES:
            try:
                resp = await self._get(_TEXTTV_API.format(page=index_page))
                data = resp.json()[0]
                plain = " ".join(data.get("content_plain") or [])
                nums = _extract_page_nums(plain)
                for n in nums:
                    if n not in seen_page_nums:
                        seen_page_nums.add(n)
                        article_pages.append((n, section))
            except Exception as e:
                logger.error("Text-TV index sida %d misslyckades: %s", index_page, e)

        if not article_pages:
            logger.warning("Text-TV: inga sidor från index, använder fallback-intervall")
            article_pages = [
                (n, "Inrikes" if n < 130 else "Utrikes" if n < 160 else "Ekonomi")
                for n in _ARTICLE_RANGE_FALLBACK
            ]

        # Steg 2: hämta artikelsidor
        articles: list[ScrapedArticle] = []

        for page_num, section in article_pages:
            if len(articles) >= limit:
                break
            try:
                resp = await self._get(_TEXTTV_API.format(page=page_num))
                data = resp.json()[0]
            except Exception as e:
                logger.warning("Text-TV sida %d misslyckades: %s", page_num, e)
                continue

            title: str = (data.get("title") or "").strip()
            if not title or title.lower() in _GENERIC_TITLES:
                continue

            # content_plain är en lista med rader — join till stycken
            plain_lines: list[str] = data.get("content_plain") or []
            full_text = "\n".join(
                line.strip() for line in plain_lines if line.strip()
            ) or None

            # Rensa bort sidhuvud ("106 SVT Text onsdag 09 apr 2026 INRIKES ...")
            if full_text:
                full_text = re.sub(
                    r'^\d{3}\s+SVT Text\s+\w+\s+\d+\s+\w+\s+\d{4}\s+',
                    '', full_text, flags=re.IGNORECASE
                ).strip()

            published_at: datetime | None = None
            ts = data.get("date_updated_unix")
            if ts:
                try:
                    published_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            url: str = data.get("permalink") or f"https://www.svt.se/text-tv/{page_num}"

            articles.append(
                ScrapedArticle(
                    url=url,
                    title=title,
                    source_slug=self.source_slug,
                    full_text=full_text,
                    published_at=published_at,
                    article_type="nyhet",
                    section=section,
                    language="sv",
                )
            )

        logger.info("SVT Text-TV: %d artiklar hämtade", len(articles))
        return articles
