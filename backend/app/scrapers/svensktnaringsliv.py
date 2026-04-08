"""
SvensktNaringlivScraper — Confederation of Swedish Enterprise.
Hämtar pressmeddelanden och analyser från pressrum + sakomraden.
Sv. Näringsliv är en Next.js-sajt (SSR) — HTML-scraping via BeautifulSoup.
"""
import logging
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedArticle

logger = logging.getLogger(__name__)

BASE_URL = "https://www.svensktnaringsliv.se"

# Svenska månadsnamn → nummer
_MONTHS_SV = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4,
    "maj": 5, "juni": 6, "juli": 7, "augusti": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}

# Sidor att scrapa för artikellänkar
_LISTING_PATHS = [
    "/pressrum/",
    "/sakomraden/arbetsmarknad/",
    "/sakomraden/ekonomisk-analys/",
    "/sakomraden/utbildning/",
]


def _parse_sv_date(text: str) -> Optional[datetime]:
    """Tolkar '16 december 2025' → datetime."""
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(_MONTHS_SV) + r")\s+(\d{4})",
        text.lower(),
    )
    if not m:
        return None
    day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
    try:
        return datetime(year, _MONTHS_SV[month_name], day)
    except ValueError:
        return None


def _extract_article_links(html: str) -> list[str]:
    """Extraherar unika artikellänkar med mönstret /xxx/title_ID.html."""
    hrefs = re.findall(r'href=["\'](/[^"\']+_\d+\.html)["\']', html)
    seen: set[str] = set()
    result: list[str] = []
    for h in hrefs:
        # Filtrera bort rena nav/member-sidor
        skip_prefixes = ("/om_oss/", "/medlem/", "/taginfo/", "/sakomraden/lonestatistik/")
        if any(h.startswith(p) for p in skip_prefixes):
            continue
        if h not in seen:
            seen.add(h)
            result.append(h)
    return result


def _parse_article_page(html: str, url: str) -> Optional[ScrapedArticle]:
    """Extraherar titel, datum och fulltext från en enskild artikelsida."""
    soup = BeautifulSoup(html, "lxml")

    # Titel
    h1 = soup.find("h1")
    if not h1:
        return None
    title = h1.get_text(strip=True)
    if not title:
        return None

    # Datum — leta efter <span> med månadsnamn
    published_at: Optional[datetime] = None
    for span in soup.find_all("span"):
        text = span.get_text(strip=True)
        date = _parse_sv_date(text)
        if date:
            published_at = date
            break

    # Fulltext från <main>
    main = soup.find("main")
    full_text: Optional[str] = None
    if main:
        # Ta bort script/style
        for tag in main.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        full_text = re.sub(r"\s+", " ", main.get_text(separator=" ", strip=True)).strip() or None

    # Sektion från URL
    parts = url.split("/")
    section = parts[3] if len(parts) > 3 else "pressrum"

    return ScrapedArticle(
        url=url,
        title=title,
        source_slug="svenskt-naringsliv",
        full_text=full_text,
        published_at=published_at,
        article_type="pressmeddelande" if "pressrum" in url else "analys",
        section=section,
        language="sv",
    )


class SvensktNaringlivScraper(BaseScraper):
    source_slug = "svenskt-naringsliv"
    base_url = BASE_URL

    async def fetch_articles(self, limit: int = 20) -> list[ScrapedArticle]:
        # Steg 1: samla artikellänkar från listningssidor
        all_links: list[str] = []
        seen_links: set[str] = set()

        for path in _LISTING_PATHS:
            if len(all_links) >= limit * 3:
                break
            try:
                resp = await self._get(f"{BASE_URL}{path}")
                links = _extract_article_links(resp.text)
                for link in links:
                    if link not in seen_links:
                        seen_links.add(link)
                        all_links.append(link)
            except Exception as e:
                logger.warning("SvNäringsliv: listningssida %s misslyckades: %s", path, e)

        if not all_links:
            logger.warning("SvNäringsliv: inga artikellänkar hittade")
            return []

        # Steg 2: hämta varje artikel
        articles: list[ScrapedArticle] = []
        for link in all_links[:limit]:
            url = f"{BASE_URL}{link}"
            try:
                resp = await self._get(url)
                article = _parse_article_page(resp.text, url)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.debug("SvNäringsliv: artikel %s misslyckades: %s", url, e)

        logger.info("SvensktNaringsliv: %d artiklar hämtade", len(articles))
        return articles
