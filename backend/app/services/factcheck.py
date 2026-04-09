"""
Faktakontroll-service — anropar Claude API för djupanalys av enskilda artiklar.
Används sparsamt (admin-only). Modell konfigurerbar via FACTCHECK_MODEL.

Analysen identifierar:
- Faktapåståenden + om de är källhänvisade
- Kvalitet på källhänvisningar (sourcing_score)
- Språklig vinkling och värdeladdade ord
- Jämförelse mot källans förväntade politiska profil
"""
import json
import logging
from typing import Optional

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Du är en opartisk faktaanalytiker specialiserad på svenska medier och politisk kommunikation.
Din uppgift är att analysera nyhetsartiklar och rapporter för faktapåståenden, källhänvisningar och politisk vinkling.
Var konkret, balanserad och basera alltid dina slutsatser på artikelns faktiska innehåll.
Svara ALLTID med giltig JSON enligt det angivna formatet — inga kommentarer utanför JSON."""

_PROMPT_TEMPLATE = """Analysera följande artikel kritiskt och returnera JSON.

KÄLLANS PROFIL:
- Politisk lutning: {political_leaning}
- Finansiering: {funding_category}
- Typ: {source_type}

ARTIKEL:
Rubrik: {title}

{full_text}

Returnera EXAKT detta JSON (inga extra fält, inga kommentarer):
{{
  "claims": [
    {{
      "text": "exakt citat eller nära parafras av påståendet",
      "attributed": true/false,
      "source_cited": "vem/vad som citeras, eller null",
      "verifiable": true/false
    }}
  ],
  "sourcing_score": 0.0,
  "framing_notes": "hur språkval och framställning färgar artikeln",
  "bias_indicators": ["konkret indikator 1", "konkret indikator 2"],
  "vs_source_profile": "stämmer innehållet med källans förväntade profil, eller avviker det?",
  "summary": "2-3 meningar som sammanfattar analysens viktigaste fynd"
}}

Definitioner:
- attributed: påståendet är explicit tillskrivet en källa i texten
- verifiable: påståendet är faktapåstående (ej ren opinion/värdering)
- sourcing_score: 0.0=inga påståenden källhänvisade, 1.0=alla källhänvisade
- Inkludera max 8 claims (välj de viktigaste)
- bias_indicators: konkreta exempel från texten, t.ex. "rubrik använder 'skandal' utan belägg\""""


def _build_prompt(
    title: str,
    full_text: str,
    political_leaning: str,
    funding_category: str,
    source_type: str,
) -> str:
    # Trunkera text om den är för lång (Claude Sonnet klarar ~200k tokens men vi håller oss till ~4000 ord)
    max_chars = 16_000
    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "\n[… text trunkerad …]"

    return _PROMPT_TEMPLATE.format(
        title=title,
        full_text=full_text,
        political_leaning=political_leaning or "okänd",
        funding_category=funding_category or "okänd",
        source_type=source_type or "okänd",
    )


async def run_factcheck(
    title: str,
    full_text: str,
    political_leaning: Optional[str] = None,
    funding_category: Optional[str] = None,
    source_type: Optional[str] = None,
) -> dict:
    """
    Anropa Claude och returnera parsad faktakontroll-dict.
    Kastar ValueError om API-nyckeln saknas.
    Kastar RuntimeError vid API-fel eller JSON-parsningsfel.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY är inte konfigurerad")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = _build_prompt(
        title=title,
        full_text=full_text or title,
        political_leaning=political_leaning,
        funding_category=funding_category,
        source_type=source_type,
    )

    logger.info("Faktakontroll startar med modell %s", settings.FACTCHECK_MODEL)

    try:
        message = await client.messages.create(
            model=settings.FACTCHECK_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error("Claude API-fel: %s", e)
        raise RuntimeError(f"Claude API-fel: {e}") from e

    raw = message.content[0].text.strip()

    # Plocka ut JSON om Claude råkat wrappa i kodblock
    if "```" in raw:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
        if m:
            raw = m.group(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON-parsningsfel: %s\nRå svar: %s", e, raw[:500])
        raise RuntimeError(f"Claude returnerade ogiltig JSON: {e}") from e

    # Normalisera
    data.setdefault("claims", [])
    data.setdefault("sourcing_score", None)
    data.setdefault("framing_notes", None)
    data.setdefault("bias_indicators", [])
    data.setdefault("vs_source_profile", None)
    data.setdefault("summary", None)

    logger.info(
        "Faktakontroll klar: %d claims, sourcing_score=%.2f",
        len(data["claims"]),
        data["sourcing_score"] or 0,
    )
    return data
