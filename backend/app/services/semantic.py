from __future__ import annotations

import asyncio
import re
from functools import lru_cache
from typing import Any

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.content import Content
from app.schemas.content import ContentOut


# ============================================================
# GENRES
# ============================================================

GENRES = {
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


GENRE_ALIASES = {
    "funny": "comedy",
    "laugh": "comedy",
    "scifi": "sci-fi",
    "sci fi": "sci-fi",
    "science fiction": "sci-fi",
    "science-fiction": "sci-fi",
    "scary": "horror",
    "romantic": "romance",
    "love story": "romance",
    "suspense": "thriller",
    "mysterious": "mystery",
    "kids": "children",
    "war movie": "war",
}


# ============================================================
# TELUGU NORMALIZATION
# ============================================================

TELUGU_REPLACEMENTS = {
    "తెలుగు": "Telugu",
    "సినిమా": "movie",
    "సినిమాలు": "movies",
    "కామెడీ": "comedy",
    "ఫన్నీ": "funny comedy",
    "హాస్యం": "comedy",
    "హారర్": "horror",
    "భయానక": "horror scary",
    "యాక్షన్": "action",
    "ప్రేమ": "romance love",
    "రొమాంటిక్": "romance",
    "థ్రిల్లర్": "thriller",
    "మిస్టరీ": "mystery",
    "డ్రామా": "drama",
    "సైన్స్ ఫిక్షన్": "sci-fi",
    "సైఫై": "sci-fi",
    "పిల్లల": "children",
    "క్రైమ్": "crime",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def contains_telugu(text: str) -> bool:
    return any(
        "\u0c00" <= ch <= "\u0c7f"
        for ch in text
    )


def normalize_query(
    query: str,
    language: str = "all",
) -> str:
    normalized = query.strip()

    for telugu, english in TELUGU_REPLACEMENTS.items():
        normalized = normalized.replace(
            telugu,
            f" {english} ",
        )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    if (
        language == "te"
        and "telugu" not in normalized.lower()
    ):
        normalized = f"Telugu {normalized}".strip()

    return normalized


def _normalize_genre(value: str) -> str:
    """Normalize catalog/query genre labels to one canonical vocabulary.

    TMDB uses labels such as ``Science Fiction`` and ``Family`` while the
    NEXUS intent parser uses ``sci-fi`` and ``children``.  Normalizing both
    sides here keeps coverage scoring and hard constraints consistent.
    """
    normalized = (
        value
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )

    normalized = re.sub(r"\s+", " ", normalized).strip()

    aliases = {
        "science fiction": "sci-fi",
        "sci fi": "sci-fi",
        "scifi": "sci-fi",
        "family": "children",
        "kids": "children",
        "kid": "children",
        "music": "musical",
    }

    return aliases.get(normalized, normalized)


def _contains_phrase(
    text: str,
    phrase: str,
) -> bool:
    return bool(
        re.search(
            rf"(?<!\w){re.escape(phrase)}(?!\w)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _is_excluded_genre(
    text: str,
    genre: str,
) -> bool:
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

    if genre == "horror":
        patterns.append(
            r"\bnot\s+scary\b"
        )

    if genre == "children":
        patterns.extend(
            [
                r"\bnot\s+kids\b",
                r"\bno\s+kids\b",
                r"\bnot\s+childish\b",
            ]
        )

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


def _normalize_aliases(text: str) -> str:
    normalized = text

    aliases = sorted(
        GENRE_ALIASES.items(),
        key=lambda row: len(row[0]),
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


def _item_genres(
    item: Content,
) -> list[str]:
    return [
        genre.strip()
        for genre in (
            item.genres
            or item.genre
            or ""
        ).split("|")
        if genre.strip()
    ]


def _item_genre_set(
    item: Content,
) -> set[str]:
    return {
        _normalize_genre(genre)
        for genre in _item_genres(item)
    }


# ============================================================
# QUERY PARSER
# ============================================================

def parse_query(
    query: str,
    language: str = "all",
) -> dict[str, Any]:

    normalized = normalize_query(
        query,
        language,
    )

    lower = normalized.lower()

    genre_text = _normalize_aliases(
        lower
    )

    excluded_genres: list[str] = []

    # Detect exclusions first.
    for genre in sorted(GENRES):
        if _is_excluded_genre(
            genre_text,
            genre,
        ):
            excluded_genres.append(
                genre
            )

    excluded_genres = sorted(
        set(excluded_genres)
    )

    # Positive required genres.
    requested_genres: list[str] = []

    for genre in sorted(GENRES):
        if genre in excluded_genres:
            continue

        if _contains_phrase(
            genre_text,
            genre,
        ):
            requested_genres.append(
                genre
            )

    requested_genres = sorted(
        set(requested_genres)
    )

    explicit_all_genres = bool(
        re.search(
            r"\b(?:both|all|must\s+(?:include|have)|with\s+(?:both|all))\b",
            lower,
            flags=re.IGNORECASE,
        )
    )
    genre_match_mode = (
        "all"
        if len(requested_genres) <= 1 or explicit_all_genres
        else "coverage"
    )

    # --------------------------------------------------------
    # Runtime
    # --------------------------------------------------------

    max_minutes = None

    hour_match = re.search(
        (
            r"(?:under|within|max(?:imum)?|"
            r"less\s+than|shorter\s+than)"
            r"\s+(\d+(?:\.\d+)?)\s*hours?"
        ),
        lower,
    )

    minute_match = re.search(
        (
            r"(?:under|within|max(?:imum)?|"
            r"less\s+than|shorter\s+than)"
            r"\s+(\d+)\s*(?:minutes?|mins?)"
        ),
        lower,
    )

    if hour_match:
        max_minutes = int(
            float(hour_match.group(1))
            * 60
        )

    elif minute_match:
        max_minutes = int(
            minute_match.group(1)
        )

    # --------------------------------------------------------
    # Session viewing budget
    #
    # "I have 3 hours" is a viewing-window preference, not the
    # same thing as "movie under 3 hours". Known movies that fit
    # the budget rank above unknown-runtime fallbacks.
    # --------------------------------------------------------

    session_budget_minutes = None

    if max_minutes is None:
        session_hour_match = re.search(
            (
                r"\b(?:i\s+have|i\s+got|got|have)\s+"
                r"(\d+(?:\.\d+)?)\s*hours?\b"
            ),
            lower,
        )

        session_minute_match = re.search(
            (
                r"\b(?:i\s+have|i\s+got|got|have)\s+"
                r"(\d+)\s*(?:minutes?|mins?)\b"
            ),
            lower,
        )

        if session_hour_match:
            session_budget_minutes = int(
                float(session_hour_match.group(1)) * 60
            )
        elif session_minute_match:
            session_budget_minutes = int(
                session_minute_match.group(1)
            )

    # --------------------------------------------------------
    # Year
    # --------------------------------------------------------

    year = None

    year_match = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        lower,
    )

    if year_match:
        year = int(
            year_match.group(1)
        )

    # --------------------------------------------------------
    # Language
    # --------------------------------------------------------

    effective_language = language

    if (
        language == "all"
        and (
            contains_telugu(query)
            or "telugu" in normalized.lower()
        )
    ):
        effective_language = "te"

    return {
        "genres":
            requested_genres,

        "required_genres":
            requested_genres,

        "genre_match_mode":
            genre_match_mode,

        "max_minutes":
            max_minutes,

        "session_budget_minutes":
            session_budget_minutes,

        "year":
            year,

        "excluded_genres":
            excluded_genres,

        "language":
            effective_language,

        "normalized_query":
            normalized,

        "runtime_note":
            (
                "Runtime constraint requires a known runtime."
                if max_minutes is not None
                else None
            ),
    }


# ============================================================
# QDRANT
# ============================================================

@lru_cache
def qdrant() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        timeout=30,
    )


@lru_cache
def embedder() -> TextEmbedding:
    return TextEmbedding(
        model_name=
            settings.embedding_model
    )


def semantic_document(
    item: Content,
) -> str:

    genres = (
        item.genres
        or item.genre
        or ""
    ).replace(
        "|",
        ", ",
    )

    tags = item.tags or ""

    language = (
        "Telugu"
        if item.original_language == "te"
        else (
            item.original_language
            or "unknown"
        )
    )

    original_title = ""

    if (
        item.original_title
        and item.original_title
        != item.title
    ):
        original_title = (
            f" Original title: "
            f"{item.original_title}."
        )

    return (
        f"Title: {item.title}."
        f"{original_title} "
        f"Language: {language}. "
        f"Genres: {genres}. "
        f"Viewer/catalog tags: {tags}. "
        f"Plot: {item.synopsis}"
    )


def _vector_search(
    query: str,
    limit: int,
) -> list[tuple[int, float]]:

    client = qdrant()

    vector = list(
        embedder().embed(
            [query]
        )
    )[0].tolist()

    response = client.query_points(
        collection_name=
            settings.qdrant_collection,

        query=
            vector,

        limit=
            limit,

        with_payload=
            True,
    )

    return [
        (
            int(point.id),
            float(point.score),
        )
        for point in response.points
    ]


async def semantic_status() -> dict[str, Any]:

    try:
        info = await asyncio.to_thread(
            qdrant().get_collection,
            settings.qdrant_collection,
        )

        return {
            "ready":
                True,

            "collection":
                settings.qdrant_collection,

            "vectors":
                int(
                    info.points_count
                    or 0
                ),

            "embedding_model":
                settings.embedding_model,
        }

    except Exception as exc:

        return {
            "ready":
                False,

            "collection":
                settings.qdrant_collection,

            "vectors":
                0,

            "embedding_model":
                settings.embedding_model,

            "message":
                (
                    "Run: docker compose exec backend "
                    "python -m app.scripts.build_semantic_index"
                ),

            "detail":
                str(exc)[:180],
        }


# ============================================================
# FILTER / SCORE HELPERS
# ============================================================

def _language_matches(
    item: Content,
    language: str,
) -> bool:

    if language == "all":
        return True

    return (
        item.original_language
        or "en"
    ).lower() == language.lower()


def _source_popularity(
    item: Content,
) -> float:

    if (
        item.catalog_source == "tmdb"
        or item.original_language == "te"
    ):
        popularity = min(
            1.0,
            max(
                0.0,
                float(
                    item.tmdb_popularity
                    or 0.0
                )
                / 100.0,
            ),
        )

        vote_confidence = min(
            1.0,
            max(
                0.0,
                float(
                    item.tmdb_vote_count
                    or 0
                )
                / 1000.0,
            ),
        )

        return (
            0.7 * popularity
            +
            0.3 * vote_confidence
        )

    return min(
        1.0,
        float(
            item.rating_count
            or 0
        )
        / 300.0,
    )


# ============================================================
# DISCOVERY SEARCH
# ============================================================

async def discovery_search(
    db: AsyncSession,
    query: str,
    user_id: int | None = None,
    limit: int = 12,
    debug: bool = False,
    source: str = "text",
    language: str = "all",
) -> dict[str, Any]:

    intent = parse_query(
        query,
        language,
    )

    effective_language = (
        intent["language"]
    )

    normalized_query = (
        intent[
            "normalized_query"
        ]
    )

    required_genres = {
        _normalize_genre(
            genre
        )
        for genre
        in intent.get(
            "required_genres",
            [],
        )
    }

    genre_match_mode = intent.get(
        "genre_match_mode",
        "all",
    )

    excluded_genres = {
        _normalize_genre(
            genre
        )
        for genre
        in intent.get(
            "excluded_genres",
            [],
        )
    }

    session_budget_minutes = intent.get(
        "session_budget_minutes"
    )

    # --------------------------------------------------------
    # Qdrant retrieval
    # --------------------------------------------------------

    try:
        vector_hits = (
            await asyncio.to_thread(
                _vector_search,
                normalized_query,
                max(
                    100,
                    limit * 10,
                ),
            )
        )

    except Exception as exc:

        return {
            "query":
                query,

            "source":
                source,

            "language":
                effective_language,

            "intent":
                intent,

            "results":
                [],

            "semantic_ready":
                False,

            "message":
                (
                    "Semantic index is not ready. "
                    "Build it after catalog import."
                ),

            "detail":
                str(exc)[:180],
        }

    ids = [
        content_id
        for content_id, _
        in vector_hits
    ]

    if not ids:

        return {
            "query":
                query,

            "source":
                source,

            "language":
                effective_language,

            "intent":
                intent,

            "results":
                [],

            "semantic_ready":
                True,

            "message":
                "No semantic matches found.",
        }

    rows = list(
        (
            await db.scalars(
                select(
                    Content
                ).where(
                    Content.id.in_(
                        ids
                    )
                )
            )
        ).all()
    )

    by_id = {
        item.id:
            item
        for item in rows
        if _language_matches(
            item,
            effective_language,
        )
    }

    semantic_scores = {
        content_id:
            score
        for content_id, score
        in vector_hits
    }

    # --------------------------------------------------------
    # Lexical expansion
    # --------------------------------------------------------

    patterns = [
        f"%{query.strip()}%"
    ]

    if (
        normalized_query.lower()
        != query.strip().lower()
    ):
        patterns.append(
            f"%{normalized_query}%"
        )

    conditions = []

    for pattern in patterns:

        conditions.extend(
            [
                Content.title.ilike(
                    pattern
                ),

                Content.original_title.ilike(
                    pattern
                ),

                Content.genre.ilike(
                    pattern
                ),

                Content.genres.ilike(
                    pattern
                ),

                Content.tags.ilike(
                    pattern
                ),

                Content.synopsis.ilike(
                    pattern
                ),
            ]
        )

    lexical_stmt = (
        select(
            Content
        ).where(
            or_(
                *conditions
            )
        )
    )

    if effective_language != "all":

        lexical_stmt = (
            lexical_stmt.where(
                Content.original_language
                == effective_language
            )
        )

    lexical_rows = list(
        (
            await db.scalars(
                lexical_stmt.limit(
                    100
                )
            )
        ).all()
    )

    for item in lexical_rows:
        by_id[
            item.id
        ] = item

    # --------------------------------------------------------
    # Redis session context
    # --------------------------------------------------------

    session_genres: dict[
        str,
        float,
    ] = {}

    if user_id:

        redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )

        try:
            values = (
                await redis.hgetall(
                    f"nexus:session:{user_id}:genres"
                )
            )

            session_genres = {
                key.lower():
                    float(value)
                for key, value
                in values.items()
            }

        except Exception:
            session_genres = {}

        finally:
            try:
                await redis.aclose()
            except Exception:
                pass

    # --------------------------------------------------------
    # HARD FILTER + RANK
    # --------------------------------------------------------

    scored = []

    rejected = []

    query_lower = (
        query
        .lower()
        .strip()
    )

    normalized_lower = (
        normalized_query
        .lower()
        .strip()
    )

    for item in by_id.values():

        item_genres = (
            _item_genres(
                item
            )
        )

        actual_genres = (
            _item_genre_set(
                item
            )
        )

        # LANGUAGE
        if not _language_matches(
            item,
            effective_language,
        ):

            rejected.append(
                {
                    "content_id":
                        item.id,

                    "title":
                        item.title,

                    "reason":
                        "language mismatch",

                    "language":
                        item.original_language,
                }
            )

            continue

        # REQUIRED GENRES
        genre_constraint_failed = (
            bool(required_genres)
            and (
                (
                    genre_match_mode == "all"
                    and not required_genres.issubset(actual_genres)
                )
                or
                (
                    genre_match_mode in {"any", "coverage"}
                    and not bool(required_genres & actual_genres)
                )
            )
        )

        if genre_constraint_failed:

            missing = (
                required_genres
                -
                actual_genres
            )

            rejected.append(
                {
                    "content_id":
                        item.id,

                    "title":
                        item.title,

                    "reason":
                        "required genre mismatch",

                    "required_genres":
                        sorted(
                            required_genres
                        ),

                    "actual_genres":
                        sorted(
                            actual_genres
                        ),

                    "missing_genres":
                        sorted(
                            missing
                        ),
                }
            )

            continue

        # EXCLUDED GENRES
        blocked = (
            excluded_genres
            &
            actual_genres
        )

        if blocked:

            rejected.append(
                {
                    "content_id":
                        item.id,

                    "title":
                        item.title,

                    "reason":
                        (
                            "excluded genre: "
                            +
                            ", ".join(
                                sorted(
                                    blocked
                                )
                            )
                        ),

                    "genres":
                        item_genres,
                }
            )

            continue

        # YEAR
        if (
            intent.get(
                "year"
            )
            and item.year
            and item.year
            != intent["year"]
        ):

            rejected.append(
                {
                    "content_id":
                        item.id,

                    "title":
                        item.title,

                    "reason":
                        (
                            "year mismatch "
                            f"(wanted "
                            f"{intent['year']})"
                        ),
                }
            )

            continue

        # ====================================================
        # STRICT RUNTIME
        #
        # If user requests "under 2 hours":
        #
        # runtime must be known
        # AND
        # runtime <= 120
        #
        # Runtime 0 is UNKNOWN, so reject it.
        # ====================================================

        max_minutes = (
            intent.get(
                "max_minutes"
            )
        )

        if max_minutes is not None:

            duration = (
                item.duration_minutes
            )

            if (
                duration is None
                or int(duration) <= 0
            ):

                rejected.append(
                    {
                        "content_id":
                            item.id,

                        "title":
                            item.title,

                        "reason":
                            (
                                "runtime unknown for "
                                "requested runtime constraint"
                            ),
                    }
                )

                continue

            if (
                int(duration)
                > int(
                    max_minutes
                )
            ):

                rejected.append(
                    {
                        "content_id":
                            item.id,

                        "title":
                            item.title,

                        "reason":
                            (
                                f"runtime "
                                f"{duration} > "
                                f"{max_minutes}"
                            ),
                    }
                )

                continue

        # ====================================================
        # SESSION BUDGET
        #
        # A known movie longer than the user's available window
        # cannot fit the session, so reject it. Unknown runtime is
        # allowed only as a fallback and is ranked below known fits.
        # ====================================================

        session_budget_fit = 0.0

        if session_budget_minutes is not None:
            duration = item.duration_minutes

            if duration is not None and int(duration) > 0:
                if int(duration) > int(session_budget_minutes):
                    rejected.append(
                        {
                            "content_id": item.id,
                            "title": item.title,
                            "reason": (
                                f"runtime {duration} exceeds "
                                f"session budget {session_budget_minutes}"
                            ),
                        }
                    )
                    continue

                session_budget_fit = 1.0

        # ----------------------------------------------------
        # Candidate passed all hard constraints
        # ----------------------------------------------------

        semantic = float(
            semantic_scores.get(
                item.id,
                0.0,
            )
        )

        searchable = " ".join(
            [
                item.title or "",
                item.original_title
                or "",
                item.tags
                or "",
                item.genres
                or "",
                item.synopsis
                or "",
            ]
        ).lower()

        lexical = (
            1.0
            if (
                query_lower
                and query_lower
                in searchable
            )
            else (
                0.85
                if (
                    normalized_lower
                    and normalized_lower
                    in searchable
                )
                else 0.0
            )
        )

        genre_overlap = (
            len(required_genres & actual_genres)
            if required_genres
            else 0
        )
        genre_match = (
            genre_overlap / len(required_genres)
            if required_genres
            else 0.0
        )

        session = max(
            (
                session_genres.get(
                    genre.lower(),
                    0.0,
                )
                for genre
                in item_genres
            ),
            default=0.0,
        )

        session = max(
            -1.0,
            min(
                1.0,
                session / 4.0,
            ),
        )

        popularity = (
            _source_popularity(
                item
            )
        )

        language_boost = (
            1.0
            if (
                effective_language
                != "all"
                and item.original_language
                == effective_language
            )
            else 0.0
        )

        final = (
            0.52 * semantic
            +
            0.16 * lexical
            +
            0.12 * genre_match
            +
            0.07 * max(
                0.0,
                session,
            )
            +
            0.05 * popularity
            +
            0.05 * language_boost
            +
            0.03 * session_budget_fit
        )

        if session < 0:
            final += (
                0.05
                * session
            )

        scored.append(
            (
                final,
                item,
                semantic,
                lexical,
                genre_match,
                session,
                popularity,
                language_boost,
                session_budget_fit,
            )
        )

    # --------------------------------------------------------
    # Suppress weak coverage fallbacks when enough stronger
    # matches exist. For 3 requested genres this means 2/3 or
    # better. We return fewer results rather than pad the rail
    # with weak 1/3 matches.
    # --------------------------------------------------------

    if genre_match_mode == "coverage" and len(required_genres) > 1:
        requested_count = len(required_genres)
        minimum_overlap = (requested_count + 1) // 2
        strong_floor = minimum_overlap / requested_count

        strong_scored = [
            row for row in scored
            if row[4] >= strong_floor
        ]

        if len(strong_scored) >= min(limit, 5):
            scored = strong_scored

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    # Coverage mode is tiered: all requested genres first, then partial coverage.
    # Within the same coverage tier, preserve the blended semantic score.
    scored.sort(
        key=lambda row: (
            row[4] if genre_match_mode == "coverage" else 0.0,
            row[8] if session_budget_minutes is not None else 0.0,
            row[0],
        ),
        reverse=True,
    )

    top = scored[
        :limit
    ]

    max_score = max(
        (
            row[0]
            for row in top
        ),
        default=1.0,
    ) or 1.0

    results = []

    for (
        final,
        item,
        semantic,
        lexical,
        genre_match,
        session,
        popularity,
        language_boost,
        session_budget_fit,
    ) in top:

        reasons = []

        if semantic >= 0.55:
            reasons.append(
                "strong semantic match"
            )

        if genre_match:
            reasons.append(
                (
                    "matches all requested genres"
                    if genre_match >= 1.0
                    else f"matches {round(genre_match * len(required_genres))}/{len(required_genres)} requested genres"
                )
            )

        if lexical:
            reasons.append(
                "catalog/title/tag match"
            )

        if language_boost:
            reasons.append(
                "matches requested language"
            )

        if session_budget_minutes is not None:
            if session_budget_fit >= 1.0:
                reasons.append(
                    f"fits {session_budget_minutes}-minute viewing window"
                )
            else:
                reasons.append(
                    "runtime unknown; fallback for viewing window"
                )

        if session > 0.15:
            reasons.append(
                "fits your live session taste"
            )

        if not reasons:
            reasons.append(
                "closest valid catalog match"
            )

        results.append(
            {
                "content":
                    ContentOut
                    .model_validate(
                        item
                    )
                    .model_dump(),

                "score":
                    round(
                        min(
                            0.99,
                            0.62
                            +
                            0.37
                            * (
                                final
                                / max_score
                            ),
                        ),
                        4,
                    ),

                "reason":
                    ", ".join(
                        reasons
                    ).capitalize(),

                "signals":
                    {
                        "semantic":
                            round(
                                semantic,
                                4,
                            ),

                        "lexical":
                            round(
                                lexical,
                                4,
                            ),

                        "genre":
                            round(
                                genre_match,
                                4,
                            ),

                        "session":
                            round(
                                session,
                                4,
                            ),

                        "popularity":
                            round(
                                popularity,
                                4,
                            ),

                        "language":
                            round(
                                language_boost,
                                4,
                            ),

                        "session_budget_fit":
                            round(
                                session_budget_fit,
                                4,
                            ),
                    },
            }
        )

    response = {
        "query":
            query,

        "normalized_query":
            normalized_query,

        "source":
            source,

        "language":
            effective_language,

        "intent":
            intent,

        "semantic_ready":
            True,

        "results":
            results,

        "message":
            (
                f"Found {len(results)} valid semantic matches "
                "after language, genre, exclusion, "
                "strict runtime, and year constraints."
            ),
    }

    if debug:

        response[
            "debug"
        ] = {
            "required_genres":
                sorted(
                    required_genres
                ),

            "excluded_genres":
                sorted(
                    excluded_genres
                ),

            "rejected_candidates":
                rejected[:50],

            "candidate_counts":
                {
                    "qdrant":
                        len(
                            vector_hits
                        ),

                    "after_merge":
                        len(
                            by_id
                        ),

                    "valid_scored":
                        len(
                            scored
                        ),

                    "returned":
                        len(
                            results
                        ),
                },

            "constraint_mode":
                (
                    f"{genre_match_mode.upper()} requested genre matching; "
                    "unknown runtimes rejected when "
                    "runtime constraint is present"
                ),
        }

    return response