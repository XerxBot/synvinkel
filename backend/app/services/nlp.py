"""
NLP-pipeline för svenska texter.
spaCy sv_core_news_sm för NER + nyckelordsbaserad topic-klassificering.
"""
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded singleton — laddas vid första scrape-jobb, inte vid startup
_nlp_lock = threading.Lock()
_nlp = None          # Language-instans när laddad, False om saknas

# Partimönster: slug → substrängar att matcha (lowercase)
PARTY_PATTERNS: dict[str, list[str]] = {
    "socialdemokraterna":  ["socialdemokraterna", "stefan löfven", "magdalena andersson", " (s)"],
    "moderaterna":         ["moderaterna", "ulf kristersson", "anna kinberg batra", " (m)"],
    "sverigedemokraterna": ["sverigedemokraterna", "jimmie åkesson", " (sd)"],
    "centerpartiet":       ["centerpartiet", "centern", "annie lööf", "muharrem demirok", " (c)"],
    "vansterpartiet":      ["vänsterpartiet", "nooshi dadgostar", " (v)"],
    "miljopartiet":        ["miljöpartiet", "märta stenevi", "per bolund", " (mp)"],
    "liberalerna":         ["liberalerna", "johan pehrson", " (l)"],
    "kristdemokraterna":   ["kristdemokraterna", "ebba busch", " (kd)"],
}


@dataclass
class NLPResult:
    topics: list[str] = field(default_factory=list)
    mentioned_parties: list[str] = field(default_factory=list)
    mentioned_persons: list[str] = field(default_factory=list)
    mentioned_orgs: list[str] = field(default_factory=list)
    sentiment_score: Optional[float] = None
    word_count: int = 0


def get_nlp():
    """Lazy-load spaCy — thread-safe singleton med double-checked locking."""
    global _nlp
    if _nlp is None:
        with _nlp_lock:
            if _nlp is None:
                try:
                    import spacy
                    logger.info("Laddar spaCy sv_core_news_sm...")
                    _nlp = spacy.load("sv_core_news_sm", disable=["parser"])
                    logger.info("spaCy laddad.")
                except (ImportError, OSError) as e:
                    logger.warning("spaCy sv_core_news_sm saknas (%s) — NER inaktiverad.", e)
                    _nlp = False
    return _nlp if _nlp else None


def strip_html(text: str) -> str:
    """Ta bort HTML-taggar och entiteter (Riksdagen anförandetext)."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z#\d]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_parties(text_lower: str) -> list[str]:
    return [
        slug
        for slug, patterns in PARTY_PATTERNS.items()
        if any(p in text_lower for p in patterns)
    ]


def enrich(text: str) -> NLPResult:
    """
    Kör NLP-pipeline på en text.
    Returnerar NLPResult med topics, entiteter och ordräkning.
    """
    from app.enrichment.topics import classify_topics

    if not text or not text.strip():
        return NLPResult()

    clean = strip_html(text)
    result = NLPResult(
        word_count=len(clean.split()),
        topics=classify_topics(clean),
        mentioned_parties=detect_parties(clean.lower()),
    )

    nlp = get_nlp()
    if nlp:
        # Cap vid 100k tecken — safe för alla verkliga artiklar
        doc = nlp(clean[:100_000])
        result.mentioned_persons = list({
            e.text.strip() for e in doc.ents
            if e.label_ == "PER" and len(e.text.strip()) > 2
        })[:50]
        result.mentioned_orgs = list({
            e.text.strip() for e in doc.ents
            if e.label_ == "ORG" and len(e.text.strip()) > 2
        })[:50]

    # Sentiment: None tills ett riktigt lexikon/modell sätts i Fas 2
    return result
