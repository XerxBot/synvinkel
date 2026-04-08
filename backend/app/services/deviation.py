"""
Avvikelsedetektering — jämför artikelns innehåll mot avsändarens politiska profil.

Returnerar deviation_score ∈ [0.0, 1.0] och flaggor lagrade i coverage_spectrum.
0.0 = fullt i linje med förväntat, 1.0 = starkt avvikande.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.organization import SourceOrganization
    from app.services.nlp import NLPResult

# Politisk tillhörighet för svenska partier
_LEFT_PARTIES = {"socialdemokraterna", "vansterpartiet", "miljopartiet"}
_RIGHT_PARTIES = {"moderaterna", "sverigedemokraterna", "kristdemokraterna", "liberalerna", "centerpartiet"}

# Förväntat sentiment-intervall per politisk lutning
# (min, max) — utanför intervallet räknas som avvikelse
_EXPECTED_SENTIMENT: dict[str, tuple[float, float]] = {
    "far-left":     (-1.0,  0.2),
    "left":         (-0.8,  0.3),
    "center-left":  (-0.5,  0.5),
    "center":       (-0.5,  0.5),
    "neutral":      (-0.5,  0.5),
    "center-right": (-0.3,  0.8),
    "right":        (-0.2,  0.9),
    "far-right":    (-0.1,  1.0),
    "libertarian":  (-0.2,  0.9),
}


def compute_deviation(
    nlp: "NLPResult",
    org: "SourceOrganization",
) -> dict:
    """
    Beräknar avvikelse mellan artikelns NLP-signaler och org:ens förväntade profil.

    Returnerar dict passande för ArticleAnalysis.coverage_spectrum:
    {
        "deviation_score": float,        # 0.0–1.0
        "sentiment_alignment": float,    # 0.0–1.0 (1 = i linje)
        "party_alignment": float,        # 0.0–1.0
        "flags": list[str],
        "version": "v0.1"
    }
    """
    flags: list[str] = []
    scores: list[float] = []

    leaning = (org.political_leaning or "neutral").lower()

    # ── 1. Sentiment-analys ──────────────────────────────────────────────────
    sentiment_alignment = 1.0
    if nlp.sentiment_score is not None:
        low, high = _EXPECTED_SENTIMENT.get(leaning, (-0.5, 0.5))
        s = nlp.sentiment_score

        if s < low:
            # Mer negativt än förväntat
            deviation = (low - s) / max(abs(low) + 1, 1)
            sentiment_alignment = max(0.0, 1.0 - deviation * 2)
            flags.append("sentiment_more_negative_than_expected")
        elif s > high:
            # Mer positivt än förväntat
            deviation = (s - high) / max(1 - high, 0.1)
            sentiment_alignment = max(0.0, 1.0 - deviation * 2)
            flags.append("sentiment_more_positive_than_expected")

    scores.append(1.0 - sentiment_alignment)

    # ── 2. Partibalans ───────────────────────────────────────────────────────
    party_alignment = 1.0
    parties = set(nlp.mentioned_parties or [])

    if parties:
        left_count = len(parties & _LEFT_PARTIES)
        right_count = len(parties & _RIGHT_PARTIES)
        total = left_count + right_count

        if total > 0:
            left_ratio = left_count / total
            right_ratio = right_count / total

            if leaning in ("right", "far-right", "libertarian", "center-right"):
                # Högerorienterad källa som mestadels nämner vänsterpartier → ovanligt
                if left_ratio > 0.7 and total >= 2:
                    party_alignment = 0.3
                    flags.append("primarily_mentions_opposing_parties")
                elif left_ratio > 0.5:
                    party_alignment = 0.7
                    flags.append("balanced_party_coverage_for_right_source")

            elif leaning in ("left", "far-left", "center-left"):
                if right_ratio > 0.7 and total >= 2:
                    party_alignment = 0.3
                    flags.append("primarily_mentions_opposing_parties")
                elif right_ratio > 0.5:
                    party_alignment = 0.7
                    flags.append("balanced_party_coverage_for_left_source")

    scores.append(1.0 - party_alignment)

    # ── 3. Sammansatt poäng ──────────────────────────────────────────────────
    deviation_score = sum(scores) / len(scores) if scores else 0.0
    deviation_score = round(min(1.0, max(0.0, deviation_score)), 3)

    if deviation_score >= 0.5:
        flags.append("high_deviation")
    elif deviation_score >= 0.25:
        flags.append("moderate_deviation")

    return {
        "deviation_score": deviation_score,
        "sentiment_alignment": round(sentiment_alignment, 3),
        "party_alignment": round(party_alignment, 3),
        "flags": flags,
        "version": "v0.1",
    }
