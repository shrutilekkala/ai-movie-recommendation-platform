from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


# ============================================================
# NEXUS 6.7.0 — UNIVERSAL EXACT + SIMILAR CONTENT VERIFIER
# ============================================================
#
# Goal:
#   Do NOT blindly trust stored genre metadata.
#   Do NOT reject a catalog genre just because a short synopsis does
#   not literally contain the requested genre word.
#
# Three outcomes:
#   VERIFIED       -> synopsis directly supports requested genre
#   CATALOG_BACKED -> synopsis is inconclusive, catalog label retained
#   REJECTED       -> synopsis strongly contradicts a suspicious label
#
# Important:
#   Stored `genre` / `genres` are never fed into the synopsis evidence
#   text. Otherwise incorrect catalog metadata would validate itself.
# ============================================================


GENRE_ALIASES = {
    "science fiction": "sci-fi",
    "science-fiction": "sci-fi",
    "sci fi": "sci-fi",
    "scifi": "sci-fi",
    "sci-fi": "sci-fi",
    "family": "children",
    "kids": "children",
    "kid": "children",
    "music": "musical",
}


GENRE_CUES: dict[str, tuple[str, ...]] = {
    "horror": (
        "ghost", "ghosts", "haunted", "haunting", "spirit", "spirits",
        "evil spirit", "vengeful spirit", "demon", "demons", "demonic",
        "possession", "possessed", "exorcism", "curse", "cursed",
        "supernatural", "paranormal", "occult", "witch", "witchcraft",
        "monster", "monsters", "zombie", "zombies", "vampire", "vampires",
        "terrifying", "terror", "nightmare", "nightmares", "ritual",
        "evil entity", "malevolent", "haunted house", "haunted palace",
    ),
    "action": (
        "fight", "fights", "fighting", "battle", "battles", "warrior",
        "soldier", "combat", "mission", "agent", "intelligence agency",
        "police", "cop", "gangster", "mafia", "criminal", "revenge",
        "assassin", "weapon", "weapons", "attack", "attacks", "rescue",
        "infiltrate", "eliminate", "special forces", "raw agent",
    ),
    "comedy": (
        "comedy", "comic", "funny", "humorous", "hilarious", "laugh",
        "laughs", "laughter", "misadventure", "misadventures", "wacky",
        "mistaken identity", "comic situations", "humor",
    ),
    "thriller": (
        "thriller", "investigation", "investigates", "investigating",
        "murder", "mystery", "conspiracy", "danger", "dangerous",
        "suspense", "suspicious", "secret", "secrets", "crime",
        "criminal", "killer", "escape", "survive", "pursuit", "threat",
    ),
    "crime": (
        "crime", "criminal", "criminals", "gangster", "gang", "mafia",
        "police", "detective", "robbery", "heist", "murder", "drug",
        "smuggler", "smuggling", "underworld", "jail", "prison",
        "corrupt", "law enforcement",
    ),
    "romance": (
        "love", "lover", "lovers", "romance", "romantic", "relationship",
        "relationships", "couple", "marriage", "married", "boyfriend",
        "girlfriend", "falls in love", "fall in love", "wedding",
    ),
    "sci-fi": (
        "science fiction", "sci-fi", "space", "spaceship", "alien", "aliens",
        "extraterrestrial", "future", "futuristic", "robot", "robots",
        "android", "artificial intelligence", "time travel", "time-travel",
        "cyber", "cyborg", "planet", "galaxy", "universe", "technology",
        "scientist", "experiment", "dystopian", "advanced technology",
    ),
    "fantasy": (
        "fantasy", "magic", "magical", "mythical", "mythology", "kingdom",
        "wizard", "sorcerer", "fairy", "god", "gods", "divine", "legend",
        "legendary", "enchanted", "superhuman power",
    ),
    "mystery": (
        "mystery", "mysterious", "investigation", "investigate", "detective",
        "clue", "clues", "secret", "secrets", "disappearance", "missing",
        "unknown", "unexplained", "discover the truth",
    ),
    "drama": (
        "family", "life", "struggle", "relationship", "emotional", "father",
        "mother", "son", "daughter", "friendship", "society", "conflict",
        "personal crisis", "family conflict",
    ),
    "war": (
        "war", "army", "soldier", "soldiers", "military", "battle",
        "battlefield", "troops", "enemy forces", "wartime",
    ),
    "adventure": (
        "adventure", "journey", "quest", "expedition", "explore",
        "exploration", "treasure", "survival", "voyage",
    ),
    "animation": (
        "animated", "animation", "cartoon", "animated characters",
    ),
    "children": (
        "children", "child", "kid", "kids", "young boy", "young girl",
        "family friendly", "family-friendly",
    ),
    "documentary": (
        "documentary", "nonfiction", "real events", "real people",
        "interviews", "factual", "true account",
    ),
    "musical": (
        "musical", "singer", "singing", "dance", "dancing", "musician",
        "songs", "music performance",
    ),
    "western": (
        "cowboy", "cowboys", "sheriff", "gunslinger", "outlaw", "frontier",
        "ranch", "western town",
    ),
    "film-noir": (
        "femme fatale", "private detective", "film noir", "noir", "fatalism",
    ),
    "imax": (
        "imax",
    ),
}


# Strong contradictions are deliberately conservative. Thriller and Mystery
# are NOT contradictions for Horror because those genres commonly overlap.
STRONG_CONTRADICTIONS: dict[str, set[str]] = {
    "horror": {"action", "crime", "comedy"},
    "sci-fi": {"romance", "comedy", "crime"},
    "documentary": {"fantasy", "horror", "sci-fi"},
    "children": {"crime", "horror"},
}


# Minimum competing evidence required before an inconclusive catalog genre can
# be rejected. This is intentionally high to avoid false negatives.
CONTRADICTION_SCORE_THRESHOLD = 0.84
MIN_SYNOPSIS_CHARS = 35


@dataclass(frozen=True)
class GenreEvidence:
    genre: str
    cue_hits: int
    cue_score: float
    cues: tuple[str, ...]


def normalize_genre(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return GENRE_ALIASES.get(normalized, normalized)


def _clean_text(value: str) -> str:
    value = str(value or "").lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9'\-\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = _clean_text(phrase)
    if not phrase:
        return False
    if " " in phrase or "-" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


@lru_cache(maxsize=8192)
def _genre_evidence_cached(text: str, genre: str) -> GenreEvidence:
    clean = _clean_text(text)
    genre = normalize_genre(genre)
    cues = GENRE_CUES.get(genre, ())

    hits = tuple(cue for cue in cues if _contains_phrase(clean, cue))

    # This is an evidence-strength scale, NOT a probability.
    if not hits:
        score = 0.0
    elif len(hits) == 1:
        score = 0.55
    elif len(hits) == 2:
        score = 0.72
    elif len(hits) == 3:
        score = 0.84
    else:
        score = 0.92

    return GenreEvidence(
        genre=genre,
        cue_hits=len(hits),
        cue_score=score,
        cues=hits[:10],
    )


def genre_evidence(text: str, genre: str) -> GenreEvidence:
    return _genre_evidence_cached(str(text or ""), normalize_genre(genre))


def _requested_genres(intent: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            normalize_genre(str(genre))
            for genre in intent.get("genres", [])
            if str(genre).strip()
        )
    )


def _catalog_genres(content: dict[str, Any]) -> set[str]:
    raw = str(content.get("genres") or content.get("genre") or "")
    return {
        normalize_genre(part)
        for part in re.split(r"[|,/]", raw)
        if part.strip()
    }


def _content_text(content: dict[str, Any]) -> str:
    # Stored genres are intentionally excluded.
    return " ".join(
        str(value or "").strip()
        for value in (
            content.get("title"),
            content.get("original_title"),
            content.get("synopsis"),
            content.get("tags"),
        )
        if str(value or "").strip()
    ).strip()


def _all_genre_evidence(text: str) -> dict[str, GenreEvidence]:
    return {
        genre: genre_evidence(text, genre)
        for genre in GENRE_CUES
    }


def _display_genre(value: str) -> str:
    if value == "sci-fi":
        return "Sci-Fi"
    if value == "film-noir":
        return "Film-Noir"
    if value == "imax":
        return "IMAX"
    return value.title()


def _effective_match_mode(
    intent: dict[str, Any],
    requested: list[str],
) -> str:
    """
    NEXUS 6.7.0 universal genre policy.

    Natural multi-genre wording means intersection:
      "English comedy sci-fi" -> comedy AND sci-fi
      "Telugu action comedy sci-fi" -> action AND comedy AND sci-fi

    Explicit disjunction means ANY:
      "action or comedy"
      "either horror or thriller"

    The orchestrator may set allow_partial_genre_match=True only while
    building the separate Similar Movies section.
    """
    if len(requested) <= 1:
        return "all"

    if bool(intent.get("allow_partial_genre_match")):
        return "coverage"

    query_text = str(
        intent.get("normalized_query")
        or intent.get("original_query")
        or ""
    ).lower()

    explicit_disjunction = bool(
        re.search(r"\b(?:or|either|any\s+of|one\s+of)\b", query_text)
    )

    if explicit_disjunction:
        return "any"

    return "all"


def verify_content_genres(
    content: dict[str, Any],
    intent: dict[str, Any],
) -> dict[str, Any]:
    """
    Calibrated runtime content-aware verification.

    Single-genre example:
      catalog Horror + explicit ghost cues -> VERIFIED
      catalog Horror + inconclusive synopsis -> CATALOG_BACKED
      catalog Horror + strong Action/Crime dominance -> REJECTED

    Natural multi-genre requests are strict intersections for exact results.
    Partial genre overlap is permitted only when the orchestrator explicitly
    builds the separate Similar Movies section.
    """

    requested = _requested_genres(intent)

    if not requested:
        return {
            "allowed": True,
            "verified": False,
            "status": "NOT_APPLICABLE",
            "reason": "No requested genres to verify",
            "requested": [],
            "supported": [],
            "catalog_backed": [],
            "unsupported": [],
            "top_content_genres": [],
            "evidence": {},
        }

    catalog = _catalog_genres(content)
    synopsis = str(content.get("synopsis") or "").strip()
    text = _content_text(content)

    effective_match_mode = _effective_match_mode(intent, requested)

    # Short descriptions are not reliable enough for destructive synopsis
    # rejection, but strict catalog intersection rules still apply.
    if len(synopsis) < MIN_SYNOPSIS_CHARS:
        overlap = [genre for genre in requested if genre in catalog]
        missing = [genre for genre in requested if genre not in catalog]
        if effective_match_mode == "all":
            allowed = set(requested).issubset(catalog)
        else:
            allowed = bool(overlap)
        return {
            "allowed": allowed,
            "verified": False,
            "status": "CATALOG_BACKED" if allowed else "REJECTED",
            "reason": (
                "Synopsis is too short for reliable verification; requested catalog genres retained"
                if allowed
                else "Required requested genre is not present in catalog metadata"
            ),
            "requested": requested,
            "supported": overlap,
            "verified_supported": [],
            "catalog_backed": overlap,
            "unsupported": missing,
            "top_content_genres": [],
            "effective_match_mode": effective_match_mode,
            "evidence": {},
        }

    evidence = _all_genre_evidence(text)
    ranked = sorted(
        evidence.values(),
        key=lambda row: (row.cue_score, row.cue_hits),
        reverse=True,
    )

    top_content_genres = [
        row.genre for row in ranked[:4] if row.cue_hits > 0
    ]

    verified_supported: list[str] = []
    catalog_backed: list[str] = []
    unsupported: list[str] = []
    diagnostics: dict[str, Any] = {}

    for genre in requested:
        row = evidence.get(
            genre,
            GenreEvidence(genre=genre, cue_hits=0, cue_score=0.0, cues=()),
        )

        catalog_support = genre in catalog

        competitors = [candidate for candidate in ranked if candidate.genre != genre]
        strongest = competitors[0] if competitors else None
        strongest_genre = strongest.genre if strongest else None
        strongest_score = strongest.cue_score if strongest else 0.0

        # Direct synopsis support always wins.
        direct_support = row.cue_hits >= 1

        contradiction_genres = STRONG_CONTRADICTIONS.get(genre, set())
        contradiction_candidates = [
            candidate
            for candidate in competitors
            if candidate.genre in contradiction_genres
        ]
        contradiction = max(
            contradiction_candidates,
            key=lambda candidate: (candidate.cue_score, candidate.cue_hits),
            default=None,
        )

        contradiction_genre = contradiction.genre if contradiction else None
        contradiction_score = contradiction.cue_score if contradiction else 0.0

        strong_contradiction = (
            catalog_support
            and not direct_support
            and contradiction is not None
            and contradiction_score >= CONTRADICTION_SCORE_THRESHOLD
        )

        if direct_support:
            state = "VERIFIED"
            genre_supported = True
            verified_supported.append(genre)

        elif catalog_support and not strong_contradiction:
            state = "CATALOG_BACKED"
            genre_supported = True
            catalog_backed.append(genre)

        else:
            state = "REJECTED"
            genre_supported = False
            unsupported.append(genre)

        diagnostics[genre] = {
            "state": state,
            "catalog_support": catalog_support,
            "cue_hits": row.cue_hits,
            "cue_score": round(row.cue_score, 4),
            "cues": list(row.cues),
            "strongest_content_genre": strongest_genre,
            "strongest_content_score": round(strongest_score, 4),
            "contradicting_genre": contradiction_genre,
            "contradicting_score": round(contradiction_score, 4),
            "strong_contradiction": strong_contradiction,
            "supported": genre_supported,
        }

    supported = verified_supported + catalog_backed
    match_mode = effective_match_mode

    if match_mode == "all":
        allowed = set(requested).issubset(set(supported))
    else:
        allowed = bool(supported)

    if not allowed:
        status = "REJECTED"
        rejected_names = ", ".join(_display_genre(g) for g in unsupported)
        strongest_conflict = None
        for genre in unsupported:
            conflict = diagnostics.get(genre, {}).get("contradicting_genre")
            score = diagnostics.get(genre, {}).get("contradicting_score", 0.0)
            if conflict and score >= CONTRADICTION_SCORE_THRESHOLD:
                strongest_conflict = (conflict, score)
                break

        if strongest_conflict:
            reason = (
                f"content-aware genre mismatch: synopsis does not support {rejected_names}; "
                f"content strongly resembles {_display_genre(strongest_conflict[0])} "
                f"({strongest_conflict[1]:.2f} evidence)"
            )
        else:
            reason = (
                f"content-aware genre mismatch: insufficient evidence for {rejected_names}"
            )

    elif verified_supported:
        status = "VERIFIED"
        names = ", ".join(_display_genre(g) for g in verified_supported)
        reason = f"Synopsis directly supports requested genre evidence: {names}"

    else:
        status = "CATALOG_BACKED"
        names = ", ".join(_display_genre(g) for g in catalog_backed)
        reason = (
            f"Synopsis is inconclusive; catalog classification retained for {names}"
        )

    return {
        "allowed": allowed,
        "verified": True,
        "status": status,
        "reason": reason,
        "requested": requested,
        "supported": supported,
        "verified_supported": verified_supported,
        "catalog_backed": catalog_backed,
        "unsupported": unsupported,
        "top_content_genres": top_content_genres,
        "effective_match_mode": match_mode,
        "evidence": diagnostics,
    }