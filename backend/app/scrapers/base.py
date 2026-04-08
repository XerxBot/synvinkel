"""
BaseScraper — abstrakt basklass för alla Synvinkel-scrapers.
Hanterar rate limiting, HTTP-klient och gemensam datastruktur.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScrapedArticle:
    url: str
    title: str
    source_slug: str = ""
    full_text: Optional[str] = None
    subtitle: Optional[str] = None
    published_at: Optional[datetime] = None
    author_names: list[str] = field(default_factory=list)
    article_type: Optional[str] = None
    section: Optional[str] = None
    language: str = "sv"


class BaseScraper(ABC):
    source_slug: str = ""
    base_url: str = ""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": settings.USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        """Hämta senaste artiklar från källan."""
        ...

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, url: str) -> httpx.Response:
        await asyncio.sleep(settings.SCRAPE_RATE_LIMIT_SECONDS)
        response = await self.client.get(url)
        response.raise_for_status()
        return response
