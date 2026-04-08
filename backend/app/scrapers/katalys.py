"""Scraper för Katalys — facklig, progressiv tankesmedja.

Använder WordPress REST API v2 (publikation-posttyp) istället för HTML-scraping.
Källa: https://www.katalys.se/wp-json/wp/v2/publikation
"""
import logging
import re
from datetime import datetime, timezone

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

WP_API_URL = "https://www.katalys.se/wp-json/wp/v2/publikation"
_FIELDS = "id,title,link,date,excerpt,content"


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z#\d]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class KatalysScraper(BaseScraper):
    source_slug = "katalys"
    base_url = "https://www.katalys.se"

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []
        page = 1
        per_page = min(limit, 100)

        while len(articles) < limit:
            try:
                resp = await self._get(
                    WP_API_URL,
                    params={
                        "per_page": per_page,
                        "page": page,
                        "_fields": _FIELDS,
                        "orderby": "date",
                        "order": "desc",
                    },
                )
                posts = resp.json()
            except Exception as e:
                logger.error("Katalys WP API misslyckades (sida %d): %s", page, e)
                break

            if not posts:
                break

            for post in posts:
                title = _strip_html(post.get("title", {}).get("rendered", "")).strip()
                url: str = post.get("link", "")
                if not title or not url:
                    continue

                raw_date = post.get("date", "")
                published_at: datetime | None = None
                if raw_date:
                    try:
                        published_at = datetime.fromisoformat(raw_date).replace(
                            tzinfo=timezone.utc
                        )
                    except ValueError:
                        pass

                # Prefer excerpt as summary, fall back to start of content
                excerpt_html = post.get("excerpt", {}).get("rendered", "")
                content_html = post.get("content", {}).get("rendered", "")
                full_text = _strip_html(content_html) or _strip_html(excerpt_html) or None

                articles.append(
                    ScrapedArticle(
                        url=url,
                        title=title,
                        source_slug=self.source_slug,
                        full_text=full_text,
                        published_at=published_at,
                        article_type="rapport",
                        section="publikationer",
                        language="sv",
                    )
                )
                if len(articles) >= limit:
                    break

            if len(posts) < per_page:
                break
            page += 1

        logger.info("Katalys: %d publikationer hämtade", len(articles))
        return articles
