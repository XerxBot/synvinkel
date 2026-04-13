"""
Samlar uttalanden för kända personer från Riksdagens öppna data API.
Gratis, strukturerad och täcker alla riksdagsledamöter och partiföreträdare.

API-dokumentation: https://data.riksdagen.se
"""
import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import SourcePerson
from app.models.statement import PersonStatement

logger = logging.getLogger(__name__)

RIKSDAGEN_API = "https://data.riksdagen.se"
REQUEST_TIMEOUT = 20.0


def _normalize_name(name: str) -> str:
    """Normalisera namn för jämförelse: lowercase, ta bort accenter, strip."""
    name = name.lower().strip()
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return name


def _strip_html(html: str) -> str:
    """Ta bort HTML-taggar och normalisera whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _fetch_all_riksdag_persons(client: httpx.AsyncClient) -> list[dict]:
    """Hämta alla personer i Riksdagens personregister."""
    url = f"{RIKSDAGEN_API}/personlista/?utformat=json&rdlstatus=samtliga"
    try:
        resp = await client.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("personlista", {}).get("person", [])
        return raw if isinstance(raw, list) else ([raw] if raw else [])
    except Exception as e:
        logger.error(f"Riksdagen personlista misslyckades: {e}")
        return []


def _find_best_match(target_name: str, riksdag_persons: list[dict]) -> Optional[str]:
    """
    Matcha ett namn mot Riksdagens personlista.
    Returnerar intressent_id om träff hittas, annars None.
    """
    target_norm = _normalize_name(target_name)
    target_parts = target_norm.split()

    best_id = None
    best_score = 0

    for person in riksdag_persons:
        first = _normalize_name(person.get("tilltalsnamn", "") or "")
        last = _normalize_name(person.get("efternamn", "") or "")
        full = f"{first} {last}".strip()

        # Exakt träff på fullständigt namn
        if full == target_norm:
            return person["intressent_id"]

        # Partiell matchning: räkna hur många namndelar som stämmer
        candidate_parts = full.split()
        matches = sum(1 for p in target_parts if p in candidate_parts)
        score = matches / max(len(target_parts), len(candidate_parts))

        if score > best_score and score >= 0.7:
            best_score = score
            best_id = person["intressent_id"]

    return best_id


async def _fetch_speech_text(
    client: httpx.AsyncClient,
    html_url: str,
    sem: asyncio.Semaphore,
) -> str:
    """Hämta och rensa texten från ett enskilt anförandes HTML-sida."""
    async with sem:
        try:
            resp = await client.get(html_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return _strip_html(resp.text)
        except Exception:
            return ""


async def _fetch_speeches(
    client: httpx.AsyncClient,
    intressent_id: str,
    max_items: int = 150,
) -> list[dict]:
    """
    Hämta anförandelista + fulltextinnehåll för en person.
    Listeندpointen innehåller bara metadata; texten hämtas via anforande_url_html.
    """
    url = (
        f"{RIKSDAGEN_API}/anforandelista/"
        f"?iid={intressent_id}&utformat=json&sz={max_items}&sort=d"
    )
    try:
        resp = await client.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("anforandelista", {}).get("anforande", [])
        speeches = raw if isinstance(raw, list) else ([raw] if raw else [])
    except Exception as e:
        logger.warning(f"  Anförandelista misslyckades för {intressent_id}: {e}")
        return []

    if not speeches:
        return []

    # Hämta fulltexten parallellt, max 5 samtida anrop
    sem = asyncio.Semaphore(5)
    html_urls = [s.get("anforande_url_html", "") for s in speeches]

    texts = await asyncio.gather(
        *[_fetch_speech_text(client, u, sem) for u in html_urls]
    )

    for speech, text in zip(speeches, texts):
        speech["_content"] = text  # injicera hämtad text

    return speeches


async def _fetch_motions(
    client: httpx.AsyncClient,
    intressent_id: str,
    sessions: list[str] | None = None,
    max_items: int = 50,
) -> list[dict]:
    """Hämta motioner för en person från Riksdagen."""
    if sessions is None:
        sessions = ["2024/25", "2023/24", "2022/23"]

    all_docs = []
    for rm in sessions:
        url = (
            f"{RIKSDAGEN_API}/dokumentlista/"
            f"?iid={intressent_id}&doktyp=mot&rm={rm}&utformat=json&sz={max_items}&sort=d"
        )
        try:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("dokumentlista", {}).get("dokument", [])
            docs = raw if isinstance(raw, list) else ([raw] if raw else [])
            all_docs.extend(docs)
        except Exception as e:
            logger.debug(f"  Motioner {rm} misslyckades för {intressent_id}: {e}")

    return all_docs[:max_items]


async def collect_person_statements(
    person: SourcePerson,
    session: AsyncSession,
    max_speeches: int = 150,
    skip_existing: bool = True,
) -> int:
    """
    Hämta uttalanden för en person från Riksdagen och lagra i person_statements.
    Returnerar antal nya rader som skapades.
    """
    async with httpx.AsyncClient(
        headers={"Accept": "application/json"},
        follow_redirects=True,
    ) as client:
        # Steg 1: hämta alla riksdagspersoner (en gång per körning — cachas i caller)
        riksdag_persons = await _fetch_all_riksdag_persons(client)
        if not riksdag_persons:
            logger.error("Kunde inte hämta Riksdagens personregister")
            return 0

        # Steg 2: matcha mot vår person
        intressent_id = _find_best_match(person.name, riksdag_persons)
        if not intressent_id:
            logger.info(f"  {person.name}: ingen match i Riksdagens personregister (inte riksdagsledamot?)")
            return 0

        logger.info(f"  {person.name}: Riksdagen intressent_id={intressent_id}")

        # Steg 3: hämta anföranden
        speeches = await _fetch_speeches(client, intressent_id, max_speeches)
        logger.info(f"  {person.name}: {len(speeches)} anföranden funna")

        created = 0
        for sp in speeches:
            content = sp.get("_content", "").strip()
            if not content or len(content) < 50:
                continue

            sp_url = sp.get("anforande_url_html", "")
            if not sp_url:
                sp_url = f"https://data.riksdagen.se/anforande/{sp.get('anforande_id', '')}/html"

            # Skip om url redan finns
            if skip_existing:
                existing = await session.scalar(
                    select(PersonStatement).where(PersonStatement.url == sp_url)
                )
                if existing:
                    continue

            dok_datum = sp.get("dok_datum") or sp.get("datum")
            pub_dt = None
            if dok_datum:
                try:
                    pub_dt = datetime.fromisoformat(dok_datum).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            title = sp.get("avsnittsrubrik") or sp.get("kammaraktivitet") or "Anförande"

            stmt = pg_insert(PersonStatement).values(
                person_id=person.id,
                platform="riksdag",
                content=content,
                url=sp_url,
                title=title,
                published_at=pub_dt,
                word_count=len(content.split()),
            )
            stmt = stmt.on_conflict_do_nothing()
            await session.execute(stmt)
            created += 1

        await session.commit()
        return created


async def collect_all_politicians(
    session: AsyncSession,
    riksdag_persons_cache: list[dict] | None = None,
) -> dict[str, int]:
    """
    Hämta uttalanden för alla politicians i DB (is_politician=True).
    Returnerar {person_name: antal_nya} dict.
    """
    from sqlalchemy import select

    politicians = (
        await session.execute(
            select(SourcePerson).where(SourcePerson.is_politician == True)
        )
    ).scalars().all()

    logger.info(f"Riksdag-insamling för {len(politicians)} politiker...")

    # Pre-fetch persons list once (shared across all persons)
    async with httpx.AsyncClient(headers={"Accept": "application/json"}, follow_redirects=True) as client:
        all_rd_persons = riksdag_persons_cache or await _fetch_all_riksdag_persons(client)

    results = {}
    for person in politicians:
        async with httpx.AsyncClient(headers={"Accept": "application/json"}, follow_redirects=True) as client:
            intressent_id = _find_best_match(person.name, all_rd_persons)
            if not intressent_id:
                logger.info(f"  {person.name}: ej i riksdagen")
                results[person.name] = 0
                continue

            speeches = await _fetch_speeches(client, intressent_id)
            logger.info(f"  {person.name}: {len(speeches)} anföranden")

            created = 0
            for sp in speeches:
                content = sp.get("_content", "").strip()
                if not content or len(content) < 50:
                    continue

                sp_url = sp.get("anforande_url_html", "")
                if not sp_url:
                    sp_url = f"https://data.riksdagen.se/anforande/{sp.get('anforande_id', '')}/html"

                existing = await session.scalar(
                    select(PersonStatement).where(PersonStatement.url == sp_url)
                )
                if existing:
                    continue

                dok_datum = sp.get("dok_datum") or sp.get("datum")
                pub_dt = None
                if dok_datum:
                    try:
                        pub_dt = datetime.fromisoformat(dok_datum).replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

                stmt = pg_insert(PersonStatement).values(
                    person_id=person.id,
                    platform="riksdag",
                    content=content,
                    url=sp_url,
                    title=sp.get("avsnittsrubrik") or sp.get("kammaraktivitet") or "Anförande",
                    published_at=pub_dt,
                    word_count=len(content.split()),
                )
                stmt = stmt.on_conflict_do_nothing()
                await session.execute(stmt)
                created += 1

            await session.commit()
            results[person.name] = created

    return results
