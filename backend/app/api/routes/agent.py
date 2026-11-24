from typing import Any
import re

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field


router = APIRouter(
    prefix="/agent",
    tags=["agent"],
)


# ============================================================
# Response models
# ============================================================

class Constraint(BaseModel):
    type: str
    value: Any


class IntentResponse(BaseModel):
    original_query: str
    normalized_query: str

    language: str | None = None

    genres: list[str] = Field(default_factory=list)
    genre_match_mode: str = "all"
    excluded_genres: list[str] = Field(default_factory=list)

    max_minutes: int | None = None
    session_budget_minutes: int | None = None
    watch_context: str | None = None

    moods: list[str] = Field(default_factory=list)

    hard_constraints: list[Constraint] = Field(default_factory=list)
    soft_preferences: list[Constraint] = Field(default_factory=list)

    parser_confidence: float


# ============================================================
# Supported genres
# ============================================================

GENRES = {
    "action",
    "adventure",
    "animation",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "fantasy",
    "horror",
    "mystery",
    "romance",
    "sci-fi",
    "thriller",
    "war",
    "western",
}


# ============================================================
# Genre aliases
# ============================================================

GENRE_ALIASES = {
    "science fiction": "sci-fi",
    "science-fiction": "sci-fi",
    "scifi": "sci-fi",
    "sci fi": "sci-fi",

    "rom-com": "romance",
    "romcom": "romance",
    "romantic comedy": "romance",

    "scary": "horror",
}


# ============================================================
# Mood vocabulary
# ============================================================

MOODS = {
    "funny": "fun",
    "fun": "fun",
    "exciting": "exciting",
    "light": "light",
    "lighthearted": "light",
    "emotional": "emotional",
    "romantic": "romantic",
    "scary": "scary",
    "dark": "dark",
    "relaxing": "relaxing",
    "feel good": "feel-good",
    "feel-good": "feel-good",
    "intense": "intense",
    "suspenseful": "suspenseful",
}


# ============================================================
# Language detection
# ============================================================

LANGUAGE_PATTERNS = {
    "telugu": "te",
    "తెలుగు": "te",

    "hindi": "hi",
    "हिंदी": "hi",

    "tamil": "ta",
    "தமிழ்": "ta",

    "english": "en",
}


# ============================================================
# Watch context
# ============================================================

WATCH_CONTEXT_PATTERNS = {
    "friends": [
        "with friends",
        "friends",
        "group watch",
        "watch with friends",
    ],

    "family": [
        "with family",
        "family movie",
        "family night",
        "watch with family",
    ],

    "date": [
        "date night",
        "with my partner",
        "with my girlfriend",
        "with my boyfriend",
        "couples",
    ],

    "solo": [
        "watching alone",
        "watch alone",
        "solo",
        "by myself",
    ],
}


# ============================================================
# Helpers
# ============================================================

def _contains_phrase(text: str, phrase: str) -> bool:
    """
    Match a phrase using word boundaries where possible.
    """

    escaped = re.escape(phrase)

    return bool(
        re.search(
            rf"(?<!\w){escaped}(?!\w)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _is_genre_excluded(text: str, genre: str) -> bool:
    """
    Detect explicit negative genre constraints.

    Examples:
        not horror
        no horror
        without horror
        exclude horror
        excluding horror
        anything but horror
    """

    escaped = re.escape(genre)

    patterns = [
        rf"\bnot\s+{escaped}\b",
        rf"\bno\s+{escaped}\b",
        rf"\bwithout\s+{escaped}\b",
        rf"\bexclude\s+{escaped}\b",
        rf"\bexcluding\s+{escaped}\b",
        rf"\banything\s+but\s+{escaped}\b",
        rf"\bexcept\s+{escaped}\b",
    ]

    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in patterns
    )


def _normalize_genre_aliases(text: str) -> str:
    """
    Normalize common genre aliases before genre extraction.
    """

    normalized = text

    aliases = sorted(
        GENRE_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for alias, canonical in aliases:
        normalized = re.sub(
            rf"(?<!\w){re.escape(alias)}(?!\w)",
            canonical,
            normalized,
            flags=re.IGNORECASE,
        )

    return normalized


# ============================================================
# Intent parser
# ============================================================

def parse_intent(query: str) -> dict:
    normalized = " ".join(query.strip().split())

    lower = normalized.lower()

    genre_text = _normalize_genre_aliases(lower)

    # --------------------------------------------------------
    # Language
    # --------------------------------------------------------

    language = None

    for keyword, code in LANGUAGE_PATTERNS.items():
        if keyword.lower() in lower:
            language = code
            break

    # --------------------------------------------------------
    # Genres
    #
    # IMPORTANT PHASE 6.3.1 FIX:
    #
    # Explicit requested genres are HARD constraints.
    #
    # "Telugu horror movie"
    #       -> require_genre=horror
    #
    # "Telugu action movie"
    #       -> require_genre=action
    #
    # "Telugu movie, not horror"
    #       -> exclude_genre=horror
    #
    # --------------------------------------------------------

    genres: list[str] = []
    excluded_genres: list[str] = []

    for genre in sorted(GENRES):

        if _is_genre_excluded(genre_text, genre):
            excluded_genres.append(genre)
            continue

        if _contains_phrase(genre_text, genre):
            genres.append(genre)

    # Remove accidental conflicts.
    genres = [
        genre
        for genre in genres
        if genre not in excluded_genres
    ]

    genres = sorted(set(genres))
    excluded_genres = sorted(set(excluded_genres))

    # One explicit genre remains strict. Multiple genres use coverage ranking:
    # 3/3 matches rank above 2/3, which rank above 1/3. Explicit all/both stays strict.
    explicit_all_genres = bool(
        re.search(
            r"\b(?:both|all|must\s+(?:include|have)|with\s+(?:both|all))\b",
            lower,
            flags=re.IGNORECASE,
        )
    )
    genre_match_mode = (
        "all"
        if len(genres) <= 1 or explicit_all_genres
        else "coverage"
    )

    # --------------------------------------------------------
    # Runtime
    # --------------------------------------------------------

    max_minutes = None
    session_budget_minutes = None

    hour_match = re.search(
        r"(?:under|within|max(?:imum)?|less\s+than|shorter\s+than)"
        r"\s+(\d+(?:\.\d+)?)\s*hours?",
        lower,
    )

    minute_match = re.search(
        r"(?:under|within|max(?:imum)?|less\s+than|shorter\s+than)"
        r"\s+(\d+)\s*(?:minutes?|mins?)",
        lower,
    )

    if hour_match:
        max_minutes = int(
            float(hour_match.group(1)) * 60
        )

    elif minute_match:
        max_minutes = int(
            minute_match.group(1)
        )

    # "I have 3 hours" describes the viewing session budget, not a per-movie cap.
    session_hour_match = re.search(
        r"\b(?:i\s+have|we\s+have|got|have)\s+(\d+(?:\.\d+)?)\s*hours?\b",
        lower,
    )
    session_minute_match = re.search(
        r"\b(?:i\s+have|we\s+have|got|have)\s+(\d+)\s*(?:minutes?|mins?)\b",
        lower,
    )
    if max_minutes is None and session_hour_match:
        session_budget_minutes = int(float(session_hour_match.group(1)) * 60)
    elif max_minutes is None and session_minute_match:
        session_budget_minutes = int(session_minute_match.group(1))

    # --------------------------------------------------------
    # Watch context
    # --------------------------------------------------------

    watch_context = None

    for context, patterns in WATCH_CONTEXT_PATTERNS.items():

        if any(
            pattern in lower
            for pattern in patterns
        ):
            watch_context = context
            break

    # --------------------------------------------------------
    # Moods
    # --------------------------------------------------------

    moods: list[str] = []

    for keyword, mood in MOODS.items():

        if _contains_phrase(lower, keyword):

            if mood not in moods:
                moods.append(mood)

    # --------------------------------------------------------
    # Hard constraints
    # --------------------------------------------------------

    hard_constraints: list[dict[str, Any]] = []

    if language:

        hard_constraints.append(
            {
                "type": "language",
                "value": language,
            }
        )

    # ========================================================
    # CRITICAL GENRE FIX
    # ========================================================
    #
    # Previously:
    #
    # for genre in genres:
    #     soft_preferences.append(...)
    #
    # That allowed semantic similarity to return movies that
    # did NOT actually belong to the requested genre.
    #
    # Now explicit genres become HARD requirements.
    # ========================================================

    if genres:
        if genre_match_mode == "all":
            for genre in genres:
                hard_constraints.append(
                    {
                        "type": "require_genre",
                        "value": genre,
                    }
                )
        else:
            hard_constraints.append(
                {
                    "type": "require_any_genre",
                    "value": genres,
                }
            )

    if max_minutes is not None:

        hard_constraints.append(
            {
                "type": "max_minutes",
                "value": max_minutes,
            }
        )

    for genre in excluded_genres:

        hard_constraints.append(
            {
                "type": "exclude_genre",
                "value": genre,
            }
        )

    # --------------------------------------------------------
    # Soft preferences
    # --------------------------------------------------------

    soft_preferences: list[dict[str, Any]] = []

    # Watch context affects ranking but does not exclude movies.

    if watch_context:

        soft_preferences.append(
            {
                "type": "watch_context",
                "value": watch_context,
            }
        )

    # Mood affects ranking but does not exclude movies.

    for mood in moods:

        soft_preferences.append(
            {
                "type": "mood",
                "value": mood,
            }
        )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    detected_signals = (
        len(hard_constraints)
        + len(soft_preferences)
    )

    confidence = min(
        0.98,
        0.55 + (detected_signals * 0.08),
    )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "original_query": query,
        "normalized_query": normalized,

        "language": language,

        "genres": genres,
        "genre_match_mode": genre_match_mode,
        "excluded_genres": excluded_genres,

        "max_minutes": max_minutes,
        "session_budget_minutes": session_budget_minutes,

        "watch_context": watch_context,

        "moods": moods,

        "hard_constraints": hard_constraints,

        "soft_preferences": soft_preferences,

        "parser_confidence": round(
            confidence,
            2,
        ),
    }


# ============================================================
# API endpoint
# ============================================================

@router.get(
    "/intent",
    response_model=IntentResponse,
    summary="Parse a natural-language entertainment request",
)
async def get_intent(
    query: str = Query(
        ...,
        min_length=1,
        description="Natural-language movie discovery request",
    ),
):
    return parse_intent(query)
# ============================================================
# OPTIONAL AUTHENTICATED USER
# ============================================================

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import AuthSession, User


async def optional_agent_user_id(
    authorization: str | None,
    db: AsyncSession,
) -> int | None:

    if (
        not authorization
        or not authorization.startswith("Bearer ")
    ):
        return None

    token = (
        authorization
        .removeprefix("Bearer ")
        .strip()
    )

    if not token:
        return None

    row = await db.execute(
        select(User.id)
        .join(
            AuthSession,
            AuthSession.user_id == User.id,
        )
        .where(
            AuthSession.token == token
        )
    )

    return row.scalar_one_or_none()


# ============================================================
# PHASE 6.3 AGENT ENDPOINT
# ============================================================

@router.get(
    "/run",
    summary="Run the NEXUS multi-tool recommendation agent",
)
async def run_nexus_agent(
    query: str = Query(
        ...,
        min_length=1,
        max_length=300,
    ),

    limit: int = Query(
        default=10,
        ge=1,
        le=20,
    ),

    authorization: str | None = Header(
        default=None,
    ),

    db: AsyncSession = Depends(
        get_db
    ),
):

    from app.services.agent_orchestrator import (
        run_agent,
    )

    user_id = await optional_agent_user_id(
        authorization,
        db,
    )

    return await run_agent(
        db=db,
        query=query,
        user_id=user_id,
        limit=limit,
    )