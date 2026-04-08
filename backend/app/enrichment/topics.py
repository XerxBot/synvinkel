"""
Enkel nyckelordsbaserad ämnesklassificering för svenska texter.
Används tills NLP-pipeline (spaCy + Gemini Flash) är på plats i Fas 1.
"""

# slug → nyckelord (minst 2 träffar krävs för klassificering)
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "politik": [
        "riksdag", "parti", "val", "regering", "minister", "statsminister",
        "opposition", "omröstning", "motion", "budgetproposition", "talman",
    ],
    "ekonomi": [
        "bnp", "inflation", "ekonomi", "ränta", "riksbank", "budget",
        "skatt", "kronor", "miljarder", "tillväxt", "recession", "konjunktur",
    ],
    "migration": [
        "migration", "invandring", "asyl", "flyktingar", "integration",
        "utvisning", "migrationsverket", "uppehållstillstånd", "ensamkommande",
    ],
    "klimat": [
        "klimat", "utsläpp", "koldioxid", "fossilfri", "vindkraft",
        "solenergi", "naturvårdsverket", "parisavtalet", "hållbarhet",
        "global uppvärmning", "koldioxidskatt",
    ],
    "brottslighet": [
        "brott", "polisen", "mord", "skjutning", "gängvåld", "rättegång",
        "dom", "fängelse", "åklagare", "brottsförebyggande", "rättsväsende",
    ],
    "utrikes": [
        "nato", "eu", "ukraina", "ryssland", "utrikespolitik", "sanktioner",
        "ambassad", "krig", "försvar", "geopolitik", "diplomati",
    ],
    "halsa": [
        "vård", "sjukhus", "vårdköer", "region", "folkhälsomyndigheten",
        "läkare", "sjuksköterska", "hälso", "tandvård", "psykisk hälsa",
    ],
    "utbildning": [
        "skolan", "lärare", "betyg", "gymnasium", "universitet",
        "skolverket", "pisa", "utbildning", "forskning", "högskola",
    ],
    "arbetsmarknad": [
        "lo", "facket", "strejk", "arbetsrätt", "lön", "sysselsättning",
        "arbetsförmedlingen", "a-kassa", "kollektivavtal", "uppsägning",
    ],
    "bostader": [
        "bostäder", "hyresrätt", "bostadspriser", "bygglov", "hyra",
        "bostadsbrist", "planprocess", "bostadsrättsförening", "renovering",
    ],
    "teknik": [
        "ai", "artificiell intelligens", "digitalisering", "tech",
        "cybersäkerhet", "data", "algoritm", "robot", "automation", "startup",
    ],
    "kultur": [
        "kultur", "film", "musik", "teater", "svt", "public service",
        "medier", "press", "journalistik", "yttrandefrihet", "konst",
    ],
    "demokrati": [
        "demokrati", "yttrandefrihet", "pressfrihet", "grundlag",
        "rättsstat", "censur", "valresultat", "valrörelse", "valdeltagande",
    ],
}


def classify_topics(text: str, threshold: int = 2) -> list[str]:
    """
    Returnera topic-slugs där minst `threshold` nyckelord matchar.
    Case-insensitive substring-matchning.
    """
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    for slug, keywords in TOPIC_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits >= threshold:
            matched.append(slug)
    return matched
