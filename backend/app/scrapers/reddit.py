"""
Scraper för Reddit r/svenskpolitik och r/sweden.
Använder Reddits publika JSON-API — inga autentiseringsuppgifter krävs.
"""
import logging
from datetime import datetime, timezone

from app.config import settings
from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

REDDIT_API_BASE = "https://www.reddit.com"


class RedditScraper(BaseScraper):
    source_slug = "reddit-svenska"
    subreddits = ["svenskpolitik", "sweden"]

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        articles: list[ScrapedArticle] = []
        per_subreddit = max(1, limit // len(self.subreddits))

        for subreddit in self.subreddits:
            fetched = await self._fetch_subreddit(subreddit, per_subreddit)
            articles.extend(fetched)

        logger.info("Reddit: %d inlägg hämtade", len(articles))
        return articles

    async def _fetch_subreddit(
        self, subreddit: str, limit: int
    ) -> list[ScrapedArticle]:
        url = (
            f"{REDDIT_API_BASE}/r/{subreddit}/new.json"
            f"?limit={limit}&t=week"
        )

        try:
            response = await self.client.get(
                url,
                headers={"User-Agent": settings.USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("Reddit r/%s: misslyckades hämta feed: %s", subreddit, e)
            return []

        articles: list[ScrapedArticle] = []

        try:
            children = data["data"]["children"]
        except (KeyError, TypeError) as e:
            logger.warning("Reddit r/%s: oväntat svar-format: %s", subreddit, e)
            return []

        for child in children:
            try:
                post = child["data"]

                score: int = post.get("score", 0)
                if score < 2:
                    continue

                permalink: str = post.get("permalink", "")
                post_url = f"{REDDIT_API_BASE}{permalink}" if permalink else post.get("url", "")

                title: str = post.get("title", "").strip()
                if not title or not post_url:
                    continue

                is_self: bool = post.get("is_self", False)
                full_text: str | None = post["selftext"].strip() if is_self else None
                if full_text == "":
                    full_text = None

                created_utc: float = post.get("created_utc", 0.0)
                published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

                author: str = post.get("author", "")
                author_names = [author] if author else []

                articles.append(
                    ScrapedArticle(
                        url=post_url,
                        title=title,
                        source_slug=self.source_slug,
                        full_text=full_text,
                        published_at=published_at,
                        author_names=author_names,
                        article_type="forum_post",
                        section=f"r/{subreddit}",
                        language="sv",
                    )
                )

            except Exception as e:
                logger.warning(
                    "Reddit r/%s: kunde inte parsa inlägg: %s", subreddit, e
                )
                continue

        logger.debug("Reddit r/%s: %d inlägg efter filtrering", subreddit, len(articles))
        return articles
