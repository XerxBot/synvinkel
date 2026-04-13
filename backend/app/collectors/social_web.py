"""
Samlar uttalanden från sociala medier, bloggar och pressreleaser.

Stödda plattformar:
  - Twitter/X   — via twscrape (kräver Twitter-konton eller guest mode)
  - Facebook     — via Meta Graph API (kräver developer access token)
  - Bloggar      — RSS-feeds och direktskrapning
  - Pressreleaser — partiwebbplatser (M, SD, S, MP, KD, L, C, V)
  - Regeringen.se — pressreleaser och tal från statsråd

Konfiguration via miljövariabler (lägg i .env):
  TWITTER_USERNAME / TWITTER_PASSWORD  — för twscrape
  FACEBOOK_ACCESS_TOKEN               — Meta Graph API long-lived token
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organization import SourcePerson
from app.models.statement import PersonStatement

logger = logging.getLogger(__name__)

# Kända Twitter/X-handles för svenska politiker och debattörer
# Utöka vid behov — slug → twitter handle
KNOWN_TWITTER_HANDLES: dict[str, str] = {
    "jimmie-akesson":           "jimmieakesson",
    "ebba-busch":               "ebbabuschor",
    "per-bolund":               "perbolund",
    "muharrem-demirok":         "demirok",
    "nooshi-dadgostar":         "nooshidad",
    "johan-pehrson":            "johanpehrson",
    "ulf-kristersson":          "ulfkristersson",
    "magdalena-andersson":      "magdalena_1971",
    "carl-bildt":               "carlbildt",
    "romina-pourmokhtari":      "romina_pm",
    "anna-tenje":               "annatenje",
    "tobias-andersson":         "tobias_sd",
    "oscar-sjostedt":           "oscarsjostedt",
}

# Kända Facebook-sid-ID för parti- och personsidor
KNOWN_FACEBOOK_PAGES: dict[str, str] = {
    "jimmie-akesson":   "JimmieAkessonSD",
    "ebba-busch":       "ebbabuschor",
    "per-bolund":       "perbolund.mp",
    "carl-bildt":       "carlbildt",
    "ulf-kristersson":  "ulfkristersson",
}

# Pressreleaser — partiernas nyhetsflöden (RSS)
# OBS: SD (sd.se) blockerar RSS med 403 — ingen fri källa tillgänglig
PARTY_RSS_FEEDS: dict[str, str] = {
    "moderaterna":        "https://moderaterna.se/feed/",
    "socialdemokraterna": "https://www.socialdemokraterna.se/feed/",
    "miljopartiet":       "https://www.mp.se/feed",
    "vansterpartiet":     "https://www.vansterpartiet.se/feed/",
    "kristdemokraterna":  "https://www.kristdemokraterna.se/feed/",
    "liberalerna":        "https://www.liberalerna.se/feed/",
    "centerpartiet":      "https://www.centerpartiet.se/feed/",
}

# Regeringen.se — tal och pressreleaser (Atom-feed)
GOVERNMENT_RSS = "https://www.regeringen.se/Filter/RssFeed?filterType=Taxonomy&filterByType=FilterablePageBase&preFilteredCategories=1014&rootPageReference=0&format=rss"


# ---------------------------------------------------------------------------
# Twitter / X  (via twscrape)
# ---------------------------------------------------------------------------

async def collect_twitter_statements(
    person: SourcePerson,
    session: AsyncSession,
    max_tweets: int = 200,
) -> int:
    """
    Hämta tweets för en person via twscrape.

    Kräver: pip install twscrape  (lägg till i pyproject.toml)
    Kräver: TWITTER_USERNAME + TWITTER_PASSWORD i .env (eller guest mode)

    twscrape skapar egna sessioner — inga officiella API-nycklar behövs.
    """
    handle = KNOWN_TWITTER_HANDLES.get(person.slug)
    if not handle:
        logger.debug(f"  {person.name}: inget känt Twitter-handle")
        return 0

    try:
        import twscrape  # type: ignore
    except ImportError:
        logger.warning("twscrape ej installerat — kör: pip install twscrape")
        return 0

    try:
        api = twscrape.API()
        # Lägg till konto om credentials finns
        username = getattr(settings, "TWITTER_USERNAME", None)
        password = getattr(settings, "TWITTER_PASSWORD", None)
        if username and password:
            await api.pool.add_account(username, password, username, password)
            await api.pool.login_all()

        created = 0
        async for tweet in api.user_tweets_and_replies(handle, limit=max_tweets):
            content = tweet.rawContent or tweet.renderedContent or ""
            if not content or len(content) < 20:
                continue
            url = f"https://x.com/{handle}/status/{tweet.id}"

            existing = await session.scalar(
                select(PersonStatement).where(PersonStatement.url == url)
            )
            if existing:
                continue

            pub_dt = tweet.date.replace(tzinfo=timezone.utc) if tweet.date else None

            stmt = pg_insert(PersonStatement).values(
                person_id=person.id,
                platform="twitter",
                content=content,
                url=url,
                title=None,
                published_at=pub_dt,
                word_count=len(content.split()),
            )
            stmt = stmt.on_conflict_do_nothing()
            await session.execute(stmt)
            created += 1

        await session.commit()
        logger.info(f"  {person.name}: {created} tweets sparade")
        return created

    except Exception as e:
        logger.warning(f"  Twitter-insamling misslyckades för {person.name}: {e}")
        return 0


# ---------------------------------------------------------------------------
# Facebook  (via Meta Graph API)
# ---------------------------------------------------------------------------

async def collect_facebook_statements(
    person: SourcePerson,
    session: AsyncSession,
    max_posts: int = 100,
) -> int:
    """
    Hämta offentliga Facebook-inlägg via Meta Graph API.

    Kräver: FACEBOOK_ACCESS_TOKEN i .env
    Skaffa: developers.facebook.com → ny app → Graph API Explorer → long-lived token
    Scope: public_content (för publika sidor)
    """
    page_id = KNOWN_FACEBOOK_PAGES.get(person.slug)
    if not page_id:
        return 0

    token = getattr(settings, "FACEBOOK_ACCESS_TOKEN", None)
    if not token:
        logger.debug("FACEBOOK_ACCESS_TOKEN saknas — hoppar över Facebook")
        return 0

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            url = (
                f"https://graph.facebook.com/v19.0/{page_id}/posts"
                f"?fields=message,story,created_time,permalink_url"
                f"&limit={max_posts}"
                f"&access_token={token}"
            )
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", [])

        created = 0
        for post in posts:
            content = post.get("message") or post.get("story") or ""
            if not content or len(content) < 20:
                continue

            post_url = post.get("permalink_url", "")
            existing = await session.scalar(
                select(PersonStatement).where(PersonStatement.url == post_url)
            )
            if existing:
                continue

            pub_str = post.get("created_time", "")
            pub_dt = None
            if pub_str:
                try:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            stmt = pg_insert(PersonStatement).values(
                person_id=person.id,
                platform="facebook",
                content=content,
                url=post_url,
                published_at=pub_dt,
                word_count=len(content.split()),
            )
            stmt = stmt.on_conflict_do_nothing()
            await session.execute(stmt)
            created += 1

        await session.commit()
        logger.info(f"  {person.name}: {created} Facebook-inlägg sparade")
        return created

    except Exception as e:
        logger.warning(f"  Facebook-insamling misslyckades för {person.name}: {e}")
        return 0


# ---------------------------------------------------------------------------
# Bloggar och partipressreleaser (RSS + direktskrapning)
# ---------------------------------------------------------------------------

def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


async def _fetch_rss_entries(url: str, max_items: int = 50) -> list[dict]:
    """Hämta RSS-feed och returnera lista med {title, content, url, published_at}."""
    try:
        import feedparser  # already in pyproject.toml

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

        entries = []
        for entry in feed.entries[:max_items]:
            content = entry.get("summary") or entry.get("content", [{}])[0].get("value", "")
            content = _strip_html(content)
            if not content:
                continue
            entries.append({
                "title": entry.get("title", ""),
                "content": content,
                "url": entry.get("link", ""),
                "published_at": _parse_date(entry.get("published")),
            })
        return entries
    except Exception as e:
        logger.debug(f"  RSS misslyckades {url}: {e}")
        return []


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


async def collect_party_pressreleases(
    person: SourcePerson,
    session: AsyncSession,
    max_items: int = 30,
) -> int:
    """
    Hämta pressreleaser från personens parti via RSS.
    Filtrera de som nämner personens namn i titel eller innehåll.
    """
    if not person.party_affiliation or not person.organization_id:
        return 0

    # Hitta rätt org_slug — vi matchar mot party_affiliation
    party_slug = _party_slug(person.party_affiliation)
    rss_url = PARTY_RSS_FEEDS.get(party_slug)
    if not rss_url:
        return 0

    entries = await _fetch_rss_entries(rss_url, max_items=100)
    name_parts = person.name.lower().split()

    created = 0
    for entry in entries:
        combined = (entry["title"] + " " + entry["content"]).lower()
        if not any(part in combined for part in name_parts):
            continue

        if entry["url"]:
            existing = await session.scalar(
                select(PersonStatement).where(PersonStatement.url == entry["url"])
            )
            if existing:
                continue

        stmt = pg_insert(PersonStatement).values(
            person_id=person.id,
            platform="press_release",
            content=entry["content"],
            url=entry["url"],
            title=entry["title"],
            published_at=entry["published_at"],
            word_count=len(entry["content"].split()),
        )
        stmt = stmt.on_conflict_do_nothing()
        await session.execute(stmt)
        created += 1

    if created:
        await session.commit()
    return created


async def collect_government_speeches(
    person: SourcePerson,
    session: AsyncSession,
) -> int:
    """
    Hämta tal och pressreleaser från regeringen.se (för statsråd).
    Filtrerar på personens namn.
    """
    entries = await _fetch_rss_entries(GOVERNMENT_RSS, max_items=200)
    name_parts = person.name.lower().split()

    created = 0
    for entry in entries:
        combined = (entry["title"] + " " + entry["content"]).lower()
        if not any(part in combined for part in name_parts):
            continue

        if entry["url"]:
            existing = await session.scalar(
                select(PersonStatement).where(PersonStatement.url == entry["url"])
            )
            if existing:
                continue

        stmt = pg_insert(PersonStatement).values(
            person_id=person.id,
            platform="press_release",
            content=entry["content"],
            url=entry["url"],
            title=entry["title"],
            published_at=entry["published_at"],
            word_count=len(entry["content"].split()),
        )
        stmt = stmt.on_conflict_do_nothing()
        await session.execute(stmt)
        created += 1

    if created:
        await session.commit()
    return created


def _party_slug(party_affiliation: str) -> str:
    mapping = {
        "Moderaterna":          "moderaterna",
        "Sverigedemokraterna":  "sverigedemokraterna",
        "Socialdemokraterna":   "socialdemokraterna",
        "Miljöpartiet":         "miljopartiet",
        "Vänsterpartiet":       "vansterpartiet",
        "Kristdemokraterna":    "kristdemokraterna",
        "Liberalerna":          "liberalerna",
        "Centerpartiet":        "centerpartiet",
    }
    for key, slug in mapping.items():
        if key.lower() in party_affiliation.lower():
            return slug
    return party_affiliation.lower()
