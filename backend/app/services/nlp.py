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

# Swedish AFINN sentiment lexicon (scores: -3 to +3)
_AFINN_SV: dict[str, int] = {
    # Positive
    "bra": 2, "utmärkt": 3, "positiv": 2, "lyckad": 2, "framgång": 2,
    "förbättring": 2, "välmående": 2, "trygg": 2, "stärker": 1, "ökar": 1,
    "gynnar": 1, "vinner": 2, "seger": 3, "löser": 2, "förbättrar": 2,
    "investerar": 1, "samarbetar": 1, "fantastisk": 3, "underbar": 3,
    "glädjande": 2, "hoppfull": 2, "framsteg": 2, "välstånd": 2,
    "trygghet": 2, "fred": 3, "rättvisa": 2, "solidaritet": 2,
    "tillväxt": 1, "stabil": 1, "förtroende": 2, "ansvar": 1,
    "respekt": 2, "öppenhet": 1, "inkludering": 1, "möjlighet": 1,
    "lösning": 2, "effektiv": 1, "hållbar": 1, "innovativ": 1,
    "stöd": 1, "hjälp": 1, "skydd": 2, "välkommen": 2, "enighet": 2,
    "demokrati": 2, "frihet": 2, "jämlikhet": 2, "mänsklig": 1,
    "välfärd": 2, "tryggare": 2, "förstärker": 1, "bygger": 1,
    "förbättrad": 2, "positiva": 2, "stärkt": 1, "framgångsrik": 2,
    "löser": 2, "skapar": 1, "satsar": 1, "prioriterar": 1,
    "förenar": 1, "leder": 1, "vinner": 2, "lyckas": 2,
    "kraftfull": 1, "tydlig": 1, "rätt": 1, "viktig": 1,
    "satsning": 1, "reform": 1, "förbund": 1, "avtal": 1,
    # Negative
    "dålig": -2, "problem": -1, "kris": -2, "kritiserar": -2,
    "misslyckad": -3, "farlig": -2, "hot": -2, "skada": -2,
    "sviker": -2, "brott": -2, "minskar": -1, "försämrar": -2,
    "motarbetar": -2, "förlorar": -2, "skandal": -3, "korrupt": -3,
    "ljuger": -3, "svek": -3, "kaos": -3, "katastrof": -3,
    "konflikt": -2, "våld": -3, "terror": -3, "rasism": -3,
    "diskriminering": -2, "orättvis": -2, "kriminell": -2, "fara": -2,
    "hotar": -2, "attackerar": -2, "saboterar": -2, "manipulerar": -2,
    "dödar": -3, "destruktiv": -3, "undergräver": -2, "försvagar": -2,
    "orättvisa": -2, "ojämlikhet": -2, "utnyttjar": -2, "exploaterar": -2,
    "förtryck": -3, "censur": -2, "propaganda": -2, "lögn": -3,
    "bedrägeri": -3, "stöld": -2, "mord": -3, "hat": -3,
    "fördomar": -2, "intolerans": -2, "extremism": -3, "radikalisering": -2,
    "missbruk": -2, "korruption": -3, "fiffel": -2, "fusk": -2,
    "kränkning": -2, "trakasseri": -2, "mobbning": -2, "utanförskap": -2,
    "fattigdom": -2, "nöd": -2, "lidande": -2, "tragedi": -3,
    "katastrof": -3, "kollaps": -3, "bankrutt": -2, "skuld": -1,
    "nedgång": -1, "försämring": -2, "stagnation": -1, "tillbakagång": -2,
    "misslyckande": -3, "förlust": -2, "kris": -2, "oro": -1,
    "orolig": -1, "osäker": -1, "instabil": -2, "hotfull": -2,
    "aggressiv": -2, "provocerar": -1, "splittrar": -2, "polariserar": -1,
    "hinder": -1, "blockerar": -1, "försenar": -1, "negligerar": -2,
}

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


def calculate_sentiment(text: str) -> Optional[float]:
    """
    Beräknar sentimentpoäng med svensk AFINN-lexikon.
    Returnerar normaliserat värde i [-1.0, 1.0], eller None om inga ord matchades.
    """
    words = re.findall(r"[a-zåäö]+", text.lower())
    raw_score = 0
    matched = 0
    for word in words:
        score = _AFINN_SV.get(word)
        if score is not None:
            raw_score += score
            matched += 1
    if matched == 0:
        return None
    normalized = raw_score / (matched * 3.0)
    return max(-1.0, min(1.0, normalized))


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

    result.sentiment_score = calculate_sentiment(clean)
    return result
