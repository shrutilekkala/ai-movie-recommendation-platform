from __future__ import annotations

import re
from typing import Any, Iterable


# ============================================================
# NEXUS 6.8.4 — MULTI-SOURCE GENRE INTELLIGENCE
# ============================================================
#
# Evidence sources:
#   1. TMDB official genres        -> baseline
#   2. TMDB movie keywords        -> strong structured evidence
#   3. TMDB overview/synopsis     -> supporting textual evidence
#   4. Manual TMDB-ID overrides   -> externally verified exception only
#
# Important policy:
#   - We ADD missing genres conservatively.
#   - We do NOT remove TMDB genres here.
#   - Runtime content_genre_verifier.py remains the final safeguard
#     against suspicious catalog labels.
#   - No movie title is hard-coded into classification.
# ============================================================


CANONICAL_GENRES = {
    "action",
    "adventure",
    "animation",
    "children",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "fantasy",
    "film-noir",
    "horror",
    "imax",
    "musical",
    "mystery",
    "romance",
    "sci-fi",
    "thriller",
    "war",
    "western",
}


GENRE_NORMALIZATION = {
    "science fiction": "sci-fi",
    "science-fiction": "sci-fi",
    "sci fi": "sci-fi",
    "scifi": "sci-fi",
    "family": "children",
    "music": "musical",
}


# Only externally verified corrections belong here.
GENRE_OVERRIDES: dict[int, list[str]] = {}


# ============================================================
# SYNOPSIS CUES
# ============================================================

SYNOPSIS_GENRE_CUES: dict[str, dict[str, float]] = {
    "action": {
        "action": 1.00,
        "fight": 0.55,
        "fights": 0.55,
        "fighting": 0.55,
        "battle": 0.65,
        "combat": 0.70,
        "warrior": 0.55,
        "assassin": 0.65,
        "mercenary": 0.55,
        "gunfight": 0.80,
        "shootout": 0.80,
        "chase": 0.45,
        "revenge": 0.35,
        "rescue": 0.30,
    },
    "adventure": {
        "adventure": 1.00,
        "journey": 0.45,
        "quest": 0.65,
        "expedition": 0.70,
        "explorer": 0.55,
        "treasure": 0.50,
        "voyage": 0.55,
        "travel through": 0.35,
    },
    "comedy": {
        "comedy": 1.00,
        "comic": 0.75,
        "comical": 0.75,
        "funny": 0.70,
        "hilarious": 0.85,
        "humorous": 0.80,
        "humour": 0.70,
        "humor": 0.70,
        "laugh": 0.50,
        "laughs": 0.50,
        "wacky": 0.55,
        "satire": 0.65,
        "satirical": 0.65,
        "misadventure": 0.50,
    },
    "crime": {
        "crime": 0.80,
        "criminal": 0.65,
        "gangster": 0.75,
        "mafia": 0.80,
        "robbery": 0.65,
        "heist": 0.75,
        "murder": 0.45,
        "detective": 0.45,
    },
    "drama": {
        "drama": 0.85,
        "family conflict": 0.65,
        "emotional": 0.50,
        "tragedy": 0.60,
    },
    "fantasy": {
        "fantasy": 1.00,
        "magical": 0.70,
        "magic": 0.60,
        "mythical": 0.70,
        "supernatural": 0.55,
        "fairy": 0.50,
        "wizard": 0.70,
        "mythology": 0.65,
    },
    "horror": {
        "horror": 1.00,
        "haunted": 0.80,
        "ghost": 0.70,
        "ghosts": 0.70,
        "demonic": 0.85,
        "demon": 0.75,
        "possession": 0.75,
        "evil spirit": 0.85,
        "terrifying": 0.75,
        "nightmare": 0.55,
    },
    "mystery": {
        "mystery": 0.90,
        "mysterious": 0.65,
        "investigation": 0.55,
        "investigate": 0.50,
        "detective": 0.60,
        "secret": 0.35,
    },
    "romance": {
        "romance": 0.90,
        "romantic": 0.80,
        "falls in love": 0.75,
        "fall in love": 0.75,
        "love story": 0.85,
        "lovers": 0.60,
    },
    "sci-fi": {
        "science fiction": 1.00,
        "sci-fi": 1.00,
        "time machine": 0.95,
        "time travel": 0.95,
        "travels through time": 0.90,
        "travel through time": 0.90,
        "future": 0.35,
        "futuristic": 0.65,
        "alien": 0.70,
        "aliens": 0.70,
        "extraterrestrial": 0.80,
        "spaceship": 0.75,
        "spacecraft": 0.75,
        "robot": 0.60,
        "robots": 0.60,
        "android": 0.60,
        "artificial intelligence": 0.70,
        "scientist": 0.30,
        "experiment": 0.30,
        "technology": 0.25,
    },
    "thriller": {
        "thriller": 0.90,
        "suspense": 0.70,
        "conspiracy": 0.55,
        "hostage": 0.55,
        "serial killer": 0.75,
        "race against time": 0.65,
    },
    "war": {
        "war": 0.70,
        "soldier": 0.55,
        "soldiers": 0.55,
        "military": 0.50,
        "army": 0.45,
        "battlefield": 0.70,
    },
    "western": {
        "western": 0.90,
        "cowboy": 0.70,
        "cowboys": 0.70,
        "gunslinger": 0.75,
        "wild west": 0.85,
    },
}


# ============================================================
# TMDB KEYWORD → GENRE EVIDENCE
#
# Keywords are structured movie metadata, so they are weighted more
# strongly than incidental overview words.
# ============================================================

KEYWORD_GENRE_CUES: dict[str, dict[str, float]] = {
    "action": {
        "action": 1.00,
        "martial arts": 0.95,
        "gunfight": 0.95,
        "shootout": 0.95,
        "fight": 0.75,
        "battle": 0.80,
        "chase": 0.70,
        "assassin": 0.85,
        "mercenary": 0.80,
        "revenge": 0.55,
        "rescue": 0.55,
        "police action": 0.90,
    },
    "adventure": {
        "adventure": 1.00,
        "quest": 0.90,
        "expedition": 0.90,
        "treasure hunt": 0.90,
        "exploration": 0.80,
        "journey": 0.65,
    },
    "comedy": {
        "comedy": 1.00,
        "dark comedy": 1.00,
        "romantic comedy": 1.00,
        "slapstick comedy": 1.00,
        "satire": 0.90,
        "parody": 0.90,
        "humor": 0.80,
        "black humor": 0.90,
        "comic relief": 0.85,
    },
    "crime": {
        "crime": 1.00,
        "organized crime": 1.00,
        "mafia": 0.95,
        "gangster": 0.95,
        "heist": 0.95,
        "robbery": 0.85,
        "criminal": 0.80,
        "detective": 0.65,
    },
    "drama": {
        "drama": 1.00,
        "family drama": 1.00,
        "melodrama": 0.95,
        "tragedy": 0.80,
    },
    "fantasy": {
        "fantasy": 1.00,
        "magic": 0.90,
        "wizard": 0.95,
        "mythology": 0.90,
        "supernatural": 0.75,
        "fairy tale": 0.90,
    },
    "horror": {
        "horror": 1.00,
        "haunted house": 1.00,
        "ghost": 0.90,
        "demon": 0.95,
        "possession": 0.95,
        "exorcism": 1.00,
        "supernatural horror": 1.00,
        "slasher": 1.00,
        "zombie": 0.95,
        "vampire": 0.95,
    },
    "mystery": {
        "mystery": 1.00,
        "whodunit": 1.00,
        "investigation": 0.80,
        "detective": 0.80,
        "missing person": 0.70,
    },
    "romance": {
        "romance": 1.00,
        "love story": 1.00,
        "romantic comedy": 0.85,
        "love triangle": 0.80,
        "first love": 0.75,
    },
    "sci-fi": {
        "science fiction": 1.00,
        "time travel": 1.00,
        "time machine": 1.00,
        "alternate history": 0.90,
        "future": 0.65,
        "dystopia": 0.90,
        "alien": 0.90,
        "extraterrestrial": 0.95,
        "space travel": 0.95,
        "spaceship": 0.90,
        "robot": 0.85,
        "android": 0.85,
        "artificial intelligence": 0.90,
        "cyborg": 0.90,
    },
    "thriller": {
        "thriller": 1.00,
        "psychological thriller": 1.00,
        "suspense": 0.90,
        "conspiracy": 0.80,
        "serial killer": 0.90,
        "hostage": 0.75,
    },
    "war": {
        "war": 1.00,
        "world war": 1.00,
        "military": 0.85,
        "soldier": 0.80,
        "battlefield": 0.90,
    },
    "western": {
        "western": 1.00,
        "cowboy": 0.90,
        "gunslinger": 0.95,
        "wild west": 1.00,
    },
}


# Conservative thresholds.
SYNOPSIS_ADD_THRESHOLD = 0.90
KEYWORD_ADD_THRESHOLD = 0.90
FUSED_ADD_THRESHOLD = 1.15
MIN_SYNOPSIS_DISTINCT_CUES = 2


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_genre_name(genre: str) -> str | None:
    cleaned = genre.strip().lower().replace("_", " ")
    cleaned = " ".join(cleaned.split())

    if not cleaned:
        return None

    cleaned = GENRE_NORMALIZATION.get(cleaned, cleaned)

    if cleaned not in CANONICAL_GENRES:
        return None

    return cleaned


def normalize_genres(genres: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for genre in genres:
        value = normalize_genre_name(genre)
        if value is None or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    return normalized


def display_genre(genre: str) -> str:
    special = {
        "sci-fi": "Science Fiction",
        "film-noir": "Film-Noir",
        "imax": "IMAX",
    }
    return special.get(genre, genre.title())


def serialize_genres(genres: Iterable[str]) -> tuple[str, str]:
    normalized = normalize_genres(genres)

    if not normalized:
        return ("Other", "Other")

    display = [display_genre(genre) for genre in normalized]
    return (display[0], "|".join(display))


def _normalize_text(value: str | None) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\s\-']", " ", text)
    return " ".join(text.split())


def _contains_cue(text: str, cue: str) -> bool:
    cue = _normalize_text(cue)
    if not cue:
        return False

    pattern = r"(?<![a-z0-9])" + re.escape(cue) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _normalize_keywords(keywords: Iterable[str] | None) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for keyword in keywords or []:
        value = _normalize_text(str(keyword))
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)

    return values


# ============================================================
# EVIDENCE SCORING
# ============================================================

def score_synopsis_genres(
    overview: str | None,
) -> dict[str, dict[str, Any]]:
    text = _normalize_text(overview)
    evidence: dict[str, dict[str, Any]] = {}

    if not text:
        return evidence

    for genre, cues in SYNOPSIS_GENRE_CUES.items():
        hits: list[str] = []
        raw_score = 0.0
        strongest = 0.0

        for cue, weight in cues.items():
            if _contains_cue(text, cue):
                hits.append(cue)
                raw_score += float(weight)
                strongest = max(strongest, float(weight))

        if hits:
            evidence[genre] = {
                "score": min(1.0, round(raw_score, 4)),
                "strongest_cue_score": round(strongest, 4),
                "cue_hits": len(hits),
                "cues": hits,
            }

    return evidence


def score_keyword_genres(
    keywords: Iterable[str] | None,
) -> dict[str, dict[str, Any]]:
    normalized_keywords = _normalize_keywords(keywords)
    keyword_blob = " | ".join(normalized_keywords)
    evidence: dict[str, dict[str, Any]] = {}

    if not normalized_keywords:
        return evidence

    for genre, cues in KEYWORD_GENRE_CUES.items():
        hits: list[str] = []
        raw_score = 0.0
        strongest = 0.0

        for cue, weight in cues.items():
            cue_normalized = _normalize_text(cue)

            # Match exact keyword or a cue phrase embedded in a keyword.
            matched = any(
                keyword == cue_normalized
                or _contains_cue(keyword, cue_normalized)
                for keyword in normalized_keywords
            )

            if matched:
                hits.append(cue)
                raw_score += float(weight)
                strongest = max(strongest, float(weight))

        if hits:
            evidence[genre] = {
                "score": min(1.0, round(raw_score, 4)),
                "strongest_cue_score": round(strongest, 4),
                "cue_hits": len(hits),
                "cues": hits,
            }

    return evidence


def enrich_genres_from_signals(
    *,
    base_genres: Iterable[str],
    overview: str | None,
    keywords: Iterable[str] | None,
) -> dict[str, Any]:
    base = normalize_genres(base_genres)
    enriched = list(base)
    added: list[str] = []

    synopsis_evidence = score_synopsis_genres(overview)
    keyword_evidence = score_keyword_genres(keywords)

    combined_debug: dict[str, Any] = {}

    for genre in CANONICAL_GENRES:
        synopsis_row = synopsis_evidence.get(genre, {})
        keyword_row = keyword_evidence.get(genre, {})

        synopsis_score = float(synopsis_row.get("score", 0.0))
        synopsis_strongest = float(
            synopsis_row.get("strongest_cue_score", 0.0)
        )
        synopsis_hits = int(synopsis_row.get("cue_hits", 0))

        keyword_score = float(keyword_row.get("score", 0.0))
        keyword_strongest = float(
            keyword_row.get("strongest_cue_score", 0.0)
        )

        # Structured TMDB keywords carry more weight than free synopsis text.
        fused_score = min(
            2.0,
            round(
                (0.60 * synopsis_score)
                + (0.95 * keyword_score),
                4,
            ),
        )

        synopsis_strong = (
            synopsis_strongest >= SYNOPSIS_ADD_THRESHOLD
            or (
                synopsis_score >= SYNOPSIS_ADD_THRESHOLD
                and synopsis_hits >= MIN_SYNOPSIS_DISTINCT_CUES
            )
        )

        keyword_strong = (
            keyword_strongest >= KEYWORD_ADD_THRESHOLD
            or keyword_score >= KEYWORD_ADD_THRESHOLD
        )

        fused_strong = (
            fused_score >= FUSED_ADD_THRESHOLD
            and synopsis_score > 0
            and keyword_score > 0
        )

        should_add = (
            genre not in enriched
            and (
                keyword_strong
                or synopsis_strong
                or fused_strong
            )
        )

        combined_debug[genre] = {
            "synopsis_score": round(synopsis_score, 4),
            "keyword_score": round(keyword_score, 4),
            "fused_score": round(fused_score, 4),
            "synopsis_cues": synopsis_row.get("cues", []),
            "keyword_cues": keyword_row.get("cues", []),
            "added": should_add,
        }

        if should_add:
            enriched.append(genre)
            added.append(genre)

    return {
        "genres": enriched,
        "added_genres": added,
        "synopsis_evidence": synopsis_evidence,
        "keyword_evidence": keyword_evidence,
        "combined_evidence": combined_debug,
        "changed": enriched != base,
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_movie_genres(
    *,
    tmdb_id: int,
    tmdb_genres: Iterable[str],
    overview: str | None = None,
    keywords: Iterable[str] | None = None,
    external_genres: Iterable[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """
    Multi-signal 6.8.2 validation.

    title is accepted for observability only. It is deliberately not used
    for classification, preventing movie-specific hard-coding.
    """
    original = normalize_genres(tmdb_genres)

    override = GENRE_OVERRIDES.get(tmdb_id)

    if override is not None:
        base = normalize_genres(override)
        base_source = "manual_override"
    else:
        base = original
        base_source = "tmdb"

    enrichment = enrich_genres_from_signals(
        base_genres=base,
        overview=overview,
        keywords=keywords,
    )

    final_genres = list(enrichment["genres"])
    added_genres = list(enrichment["added_genres"])
    normalized_external = normalize_genres(external_genres or [])
    external_added = []
    for genre in normalized_external:
        if genre not in final_genres:
            final_genres.append(genre)
            external_added.append(genre)
            if genre not in added_genres:
                added_genres.append(genre)

    if external_added and enrichment["added_genres"]:
        source = f"{base_source}+multi_signal+wikidata"
    elif external_added:
        source = f"{base_source}+wikidata"
    elif added_genres:
        source = f"{base_source}+multi_signal"
    else:
        source = base_source

    return {
        "genres": final_genres,
        "source": source,
        "original_genres": original,
        "base_genres": base,
        "added_genres": added_genres,
        "synopsis_evidence": enrichment["synopsis_evidence"],
        "keyword_evidence": enrichment["keyword_evidence"],
        "combined_evidence": enrichment["combined_evidence"],
        "external_genres": normalized_external,
        "external_added_genres": external_added,
        "changed": final_genres != original,
        "title": title,
    }
