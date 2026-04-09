"""
SVT Nyheter-scraper — RSS-flöden + trafilatura för fulltextextraktion.
SVT är public service och har öppna RSS-flöden utan autentisering.
Hämtar från inrikes, utrikes och ekonomi för bred täckning.
"""
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import trafilatura

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

_SVT_RSS_FEEDS = [
    ("https://www.svt.se/nyheter/rss.xml",         "Inrikes"),
    ("https://www.svt.se/nyheter/utrikes/rss.xml", "Utrikes"),
    ("https://www.svt.se/nyheter/ekonomi/rss.xml", "Ekonomi"),
]


def _parse_rss_date(entry: dict) -> datetime | None:
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    return None


class SVTScraper(BaseScraper):
    source_slug = "svt-nyheter"
    base_url = "https://www.svt.se"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []
        seen_urls: set[str] = set()

        for feed_url, section in _SVT_RSS_FEEDS:
            if len(articles) >= limit:
                break
            try:
                resp = await self._get(feed_url)
                feed = feedparser.parse(resp.content)
            except Exception as e:
                logger.error("SVT RSS misslyckades (%s): %s", feed_url, e)
                continue

            for entry in feed.entries:
                if len(articles) >= limit:
                    break

                url: str = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title: str = entry.get("title", "").strip()
                if not title:
                    continue

                summary: str = entry.get("summary", "").strip()
                published_at = _parse_rss_date(entry)

                # Hämta fulltext — trafilatura extraherar artikelinnehåll
                # utan navigering, sidebars och reklam
                full_text: str | None = None
                try:
                    article_resp = await self._get(url)
                    full_text = trafilatura.extract(
                        article_resp.text,
                        include_comments=False,
                        include_tables=False,
                        favor_precision=True,
                    )
                except Exception as e:
                    logger.warning("SVT fulltextextraktion misslyckades (%s): %s", url, e)
                    full_text = summary or None

                articles.append(
                    ScrapedArticle(
                        url=url,
                        title=title,
                        source_slug=self.source_slug,
                        full_text=full_text or summary or None,
                        subtitle=summary or None,
                        published_at=published_at,
                        article_type="nyhet",
                        section=section,
                        language="sv",
                    )
                )

        logger.info("SVT: %d artiklar hämtade", len(articles))
        return articles
