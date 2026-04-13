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

_TWITTER_USER_CACHE: dict[str, str] = {}  # handle → user_id


async def _twitter_get_user_id(client: httpx.AsyncClient, handle: str) -> Optional[str]:
    """Slå upp Twitter user_id för ett handle via API v2."""
    if handle in _TWITTER_USER_CACHE:
        return _TWITTER_USER_CACHE[handle]
    resp = await client.get(f"https://api.twitter.com/2/users/by/username/{handle}")
    if resp.status_code != 200:
        logger.warning(f"  Twitter user lookup misslyckades för @{handle}: {resp.status_code} {resp.text[:100]}")
        return None
    data = resp.json().get("data", {})
    uid = data.get("id")
    if uid:
        _TWITTER_USER_CACHE[handle] = uid
    return uid


async def collect_twitter_statements(
    person: SourcePerson,
    session: AsyncSession,
    max_tweets: int = 200,
) -> int:
    """
    Hämta tweets via Twitter API v2 (Bearer Token — app-only auth).
    Kräver: TWITTER_BEARER_TOKEN i .env
    """
    handle = KNOWN_TWITTER_HANDLES.get(person.slug)
    if not handle:
        logger.debug(f"  {person.name}: inget känt Twitter-handle")
        return 0

    bearer = getattr(settings, "TWITTER_BEARER_TOKEN", None)
    if not bearer:
        logger.debug("TWITTER_BEARER_TOKEN saknas — hoppar över Twitter")
        return 0

    headers = {
        "Authorization": f"Bearer {bearer}",
        "User-Agent": settings.USER_AGENT,
    }

    try:
        async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
            user_id = await _twitter_get_user_id(client, handle)
            if not user_id:
                return 0

            created = 0
            pagination_token: Optional[str] = None
            fetched = 0

            while fetched < max_tweets:
                batch = min(100, max_tweets - fetched)
                params: dict = {
                    "max_results": batch,
                    "tweet.fields": "created_at,text",
                    "exclude": "retweets",
                }
                if pagination_token:
                    params["pagination_token"] = pagination_token

                resp = await client.get(
                    f"https://api.twitter.com/2/users/{user_id}/tweets",
                    params=params,
                )
                if resp.status_code == 429:
                    logger.warning(f"  Twitter rate limit nådd för {person.name} — avbryter")
                    break
                if resp.status_code != 200:
                    logger.warning(f"  Twitter tweets-hämtning misslyckades: {resp.status_code} {resp.text[:100]}")
                    break

                body = resp.json()
                tweets = body.get("data", [])
                fetched += len(tweets)

                for tweet in tweets:
                    content = tweet.get("text", "")
                    if not content or len(content) < 20:
                        continue
                    tweet_id = tweet.get("id", "")
                    url = f"https://x.com/{handle}/status/{tweet_id}"

                    existing = await session.scalar(
                        select(PersonStatement).where(PersonStatement.url == url)
                    )
                    if existing:
                        continue

                    pub_dt = None
                    if ts := tweet.get("created_at"):
                        try:
                            pub_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        except ValueError:
                            pass

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

                meta = body.get("meta", {})
                pagination_token = meta.get("next_token")
                if not pagination_token or not tweets:
                    break

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
