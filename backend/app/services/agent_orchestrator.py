from __future__ import annotations

import json
import re
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.agent import parse_intent
from app.core.config import settings

from app.models.user import (
    User,
    UserContentState,
)

from app.models.content import Content

from app.services.recommender import (
    nexus_recommendations,
)

from app.services.semantic import (
    discovery_search,
)

from app.services.content_genre_verifier import (
    verify_content_genres,
)


# ============================================================
# USER PROFILE
# ============================================================

async def get_user_profile(
    db: AsyncSession,
    user_id: int | None,
) -> dict[str, Any]:

    if user_id is None:

        return {
            "authenticated": False,
            "favorite_genres": [],
            "liked_content_ids": [],
            "disliked_content_ids": [],
            "my_list_content_ids": [],
        }

    user = await db.get(
        User,
        user_id,
    )

    if user is None:

        return {
            "authenticated": False,
            "favorite_genres": [],
            "liked_content_ids": [],
            "disliked_content_ids": [],
            "my_list_content_ids": [],
        }

    states = list(
        (
            await db.scalars(
                select(
                    UserContentState
                ).where(
                    UserContentState.user_id
                    == user_id
                )
            )
        ).all()
    )

    favorite_genres = [
        genre.strip()
        for genre in (
            user.favorite_genres
            or ""
        ).split(",")
        if genre.strip()
    ]

    return {
        "authenticated":
            True,

        "user_id":
            user.id,

        "display_name":
            user.display_name,

        "favorite_genres":
            favorite_genres,

        "liked_content_ids":
            [
                state.content_id
                for state in states
                if state.reaction
                == "like"
            ],

        "disliked_content_ids":
            [
                state.content_id
                for state in states
                if state.reaction
                == "dislike"
            ],

        "my_list_content_ids":
            [
                state.content_id
                for state in states
                if bool(
                    state.in_my_list
                )
            ],
    }


# ============================================================
# REDIS SESSION
# ============================================================

async def get_session_context(
    user_id: int | None,
) -> dict[str, Any]:

    if user_id is None:

        return {
            "available": False,
            "event_count": 0,
            "genre_affinity": [],
            "recent_events": [],
        }

    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )

    key = (
        f"nexus:session:{user_id}"
    )

    try:

        genres = await redis.hgetall(
            f"{key}:genres"
        )

        metadata = await redis.hgetall(
            key
        )

        raw_events = await redis.lrange(
            f"{key}:events",
            0,
            9,
        )

        genre_affinity = sorted(
            [
                {
                    "genre":
                        genre,

                    "score":
                        round(
                            float(score),
                            3,
                        ),
                }

                for genre, score
                in genres.items()
            ],
            key=lambda row:
                row["score"],
            reverse=True,
        )

        recent_events = []

        for event in raw_events:

            try:
                recent_events.append(
                    json.loads(
                        event
                    )
                )

            except json.JSONDecodeError:
                continue

        return {
            "available":
                bool(
                    genres
                    or metadata
                    or raw_events
                ),

            "event_count":
                int(
                    metadata.get(
                        "event_count",
                        0,
                    )
                ),

            "last_event_type":
                metadata.get(
                    "last_event_type"
                ),

            "updated_at":
                metadata.get(
                    "updated_at"
                ),

            "genre_affinity":
                genre_affinity,

            "recent_events":
                recent_events,
        }

    except Exception as exc:

        return {
            "available":
                False,

            "event_count":
                0,

            "genre_affinity":
                [],

            "recent_events":
                [],

            "error":
                str(exc)[:160],
        }

    finally:

        try:
            await redis.aclose()

        except Exception:
            pass


# ============================================================
# GENRE HELPERS
# ============================================================

def normalize_genre(
    value: str,
) -> str:
    """Normalize query and catalog genre names before comparison.

    This bridges TMDB labels (for example ``Science Fiction``) with the
    canonical names produced by the NEXUS intent parser (``sci-fi``).
    """
    normalized = (
        value
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )

    normalized = " ".join(normalized.split())

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


def content_genres(
    content: dict[str, Any],
) -> set[str]:

    return {
        normalize_genre(
            genre
        )

        for genre in (
            content.get(
                "genres"
            )
            or content.get(
                "genre"
            )
            or ""
        ).split("|")

        if genre.strip()
    }


def effective_genre_match_mode(
    intent: dict[str, Any],
) -> str:
    """
    Universal 6.7.0 genre semantics.

    Normal multi-genre wording means ALL requested genres.
    Explicit OR/either/any-of wording means ANY.
    Similar-result generation may explicitly enable partial matching.
    """
    requested = [
        normalize_genre(str(genre))
        for genre in intent.get("genres", [])
        if str(genre).strip()
    ]

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

    return "any" if explicit_disjunction else "all"


def requested_genre_details(
    content: dict[str, Any],
    intent: dict[str, Any],
) -> tuple[list[str], list[str], float]:
    requested = [
        normalize_genre(str(genre))
        for genre in intent.get("genres", [])
        if str(genre).strip()
    ]
    requested = list(dict.fromkeys(requested))

    if not requested:
        return [], [], 0.0

    actual = content_genres(content)
    matched = [genre for genre in requested if genre in actual]
    missing = [genre for genre in requested if genre not in actual]
    coverage = len(matched) / len(requested)

    return matched, missing, coverage


# ============================================================
# HARD CONSTRAINT VALIDATOR
# ============================================================

def satisfies_hard_constraints(
    content: dict[str, Any],
    intent: dict[str, Any],
) -> tuple[
    bool,
    list[str],
]:

    reasons: list[str] = []

    # --------------------------------------------------------
    # LANGUAGE
    # --------------------------------------------------------

    language = (
        intent.get(
            "language"
        )
    )

    if language:

        actual_language = (
            content.get(
                "original_language"
            )
            or "en"
        ).lower()

        if (
            actual_language
            != language.lower()
        ):

            reasons.append(
                (
                    "language mismatch: "
                    f"wanted {language}, "
                    f"got {actual_language}"
                )
            )

    actual_genres = (
        content_genres(
            content
        )
    )

    # --------------------------------------------------------
    # REQUIRED GENRES
    # --------------------------------------------------------

    required_genres = {
        normalize_genre(
            str(
                genre
            )
        )

        for genre in intent.get(
            "genres",
            [],
        )

        if str(
            genre
        ).strip()
    }

    genre_match_mode = effective_genre_match_mode(
        intent
    )

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

        reasons.append(
            (
                "required genre mismatch: "
                "missing "
                +
                ", ".join(
                    sorted(
                        missing
                    )
                )
            )
        )

    # --------------------------------------------------------
    # EXCLUDED GENRES
    # --------------------------------------------------------

    excluded_genres = {
        normalize_genre(
            str(
                genre
            )
        )

        for genre in intent.get(
            "excluded_genres",
            [],
        )

        if str(
            genre
        ).strip()
    }

    blocked = (
        excluded_genres
        &
        actual_genres
    )

    if blocked:

        reasons.append(
            (
                "excluded genre: "
                +
                ", ".join(
                    sorted(
                        blocked
                    )
                )
            )
        )

    # ========================================================
    # STRICT RUNTIME
    #
    # User says:
    # "under 2 hours"
    #
    # Then:
    # runtime must be KNOWN
    # AND runtime <= 120.
    #
    # Runtime 0 is UNKNOWN and must be rejected.
    # ========================================================

    max_minutes = (
        intent.get(
            "max_minutes"
        )
    )

    if max_minutes is not None:

        duration = (
            content.get(
                "duration_minutes"
            )
        )

        if (
            duration is None
            or int(duration) <= 0
        ):

            reasons.append(
                (
                    "runtime unknown for "
                    "requested runtime constraint"
                )
            )

        elif (
            int(duration)
            > int(
                max_minutes
            )
        ):

            reasons.append(
                (
                    f"runtime "
                    f"{duration} > "
                    f"{max_minutes}"
                )
            )

    session_budget_minutes = intent.get(
        "session_budget_minutes"
    )

    if session_budget_minutes is not None:
        duration = content.get(
            "duration_minutes"
        )

        # Known movies that exceed the available viewing window
        # cannot satisfy the request. Unknown runtime remains a
        # fallback and is ranked below known fits later.
        if (
            duration is not None
            and int(duration) > 0
            and int(duration) > int(session_budget_minutes)
        ):
            reasons.append(
                (
                    f"runtime {duration} exceeds "
                    f"session budget {session_budget_minutes}"
                )
            )

    return (
        len(reasons) == 0,
        reasons,
    )


# ============================================================
# REQUESTED GENRE SCORE
# ============================================================

def requested_genre_score(
    content: dict[str, Any],
    intent: dict[str, Any],
) -> float:

    requested = {
        normalize_genre(
            str(
                genre
            )
        )

        for genre in intent.get(
            "genres",
            [],
        )

        if str(
            genre
        ).strip()
    }

    if not requested:

        return 0.0

    actual = (
        content_genres(
            content
        )
    )

    overlap = len(
        requested
        & actual
    )

    return overlap / len(requested)


def session_budget_fit_score(
    content: dict[str, Any],
    intent: dict[str, Any],
) -> float:

    budget = intent.get(
        "session_budget_minutes"
    )

    if budget is None:
        return 0.0

    duration = content.get(
        "duration_minutes"
    )

    if duration is None or int(duration) <= 0:
        return 0.0

    return 1.0 if int(duration) <= int(budget) else -1.0


# ============================================================
# SESSION SCORE
# ============================================================

def session_genre_score(
    content: dict[str, Any],
    session: dict[str, Any],
) -> float:

    affinities = {
        normalize_genre(
            str(
                row[
                    "genre"
                ]
            )
        ):
            float(
                row[
                    "score"
                ]
            )

        for row in session.get(
            "genre_affinity",
            [],
        )
    }

    genres = (
        content_genres(
            content
        )
    )

    if not genres:

        return 0.0

    raw = max(
        (
            affinities.get(
                genre,
                0.0,
            )

            for genre in genres
        ),
        default=0.0,
    )

    return max(
        -1.0,
        min(
            1.0,
            raw / 3.0,
        ),
    )


# ============================================================
# CONTENT SERIALIZER
# ============================================================

def content_to_dict(
    raw_content: Any,
) -> dict[str, Any]:

    if raw_content is None:
        return {}

    if isinstance(
        raw_content,
        dict,
    ):
        return dict(
            raw_content
        )

    if hasattr(
        raw_content,
        "__table__",
    ):

        return {
            column.name:
                getattr(
                    raw_content,
                    column.name,
                )

            for column
            in raw_content
            .__table__
            .columns
        }

    return {}


# ============================================================
# CATALOG-FIRST EXACT DISCOVERY
# ============================================================

async def discover_exact_catalog_candidates(
    db: AsyncSession,
    intent: dict[str, Any],
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Search PostgreSQL BEFORE semantic ranking for natural multi-genre
    intersections.

    This fixes the 6.7.0 recall bug where a true exact title could never
    become an exact result unless Qdrant/recommender happened to retrieve it.

    We intentionally load a bounded language-level catalog slice and apply
    the existing Python constraint/verifier logic. This avoids coupling the
    implementation to a specific SQL genre storage representation.
    """
    requested = [
        normalize_genre(str(genre))
        for genre in intent.get("genres", [])
        if str(genre).strip()
    ]
    requested = list(dict.fromkeys(requested))

    if not requested:
        return []

    # Explicit OR queries do not need strict intersection expansion.
    if effective_genre_match_mode(intent) != "all":
        return []

    stmt = select(Content)

    language = intent.get("language")
    if language:
        stmt = stmt.where(
            Content.original_language == str(language).lower()
        )

    # Keep the scan bounded but substantially wider than semantic top-k.
    # Exact metadata checks below determine actual eligibility.
    scan_limit = max(int(limit) * 25, 500)
    raw_rows = list((await db.scalars(stmt.limit(scan_limit))).all())

    discovered: list[dict[str, Any]] = []

    for raw_content in raw_rows:
        content = content_to_dict(raw_content)
        if not content or content.get("id") is None:
            continue

        actual = content_genres(content)
        if not set(requested).issubset(actual):
            continue

        allowed, _ = satisfies_hard_constraints(content, intent)
        if not allowed:
            continue

        verification = verify_content_genres(content, intent)
        if not verification.get("allowed", True):
            continue

        supported = {
            normalize_genre(str(genre))
            for genre in (
                verification.get("verified_supported", [])
                + verification.get("catalog_backed", [])
            )
        }

        # When the verifier provides support information, an exact result
        # must still support the complete requested intersection.
        if supported and not set(requested).issubset(supported):
            continue

        discovered.append(
            {
                "content": content,
                # Catalog discovery is not a semantic score. Give it zero
                # here; exactness/verification is handled independently.
                "score": 0.0,
                "reason": "Exact catalog genre-combination discovery",
                "source": "catalog_exact",
            }
        )

        if len(discovered) >= max(limit * 4, 40):
            break

    return discovered


# ============================================================
# MERGE CANDIDATES
# ============================================================

def merge_candidates(
    semantic_results: list[dict[str, Any]],
    recommendation_results: list[dict[str, Any]],
    exact_catalog_results: list[dict[str, Any]],
    intent: dict[str, Any],
    session: dict[str, Any],
    limit: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Build two independent result groups.

    results:
        Exact matches for natural multi-genre queries.
        For explicit OR queries, valid ANY matches are treated as exact
        because they satisfy the user's stated disjunction.

    similar_results:
        Same-language candidates that satisfy non-genre hard constraints
        and overlap at least one requested genre, but do not satisfy the
        full natural-language genre intersection.
    """

    candidates: dict[int, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # COLLECT CATALOG-FIRST EXACT CANDIDATES
    # --------------------------------------------------------

    for result in exact_catalog_results:
        content = content_to_dict(result.get("content"))
        content_id = content.get("id")

        if content_id is None:
            continue

        row = candidates.setdefault(
            int(content_id),
            {
                "content": content,
                "semantic_score": 0.0,
                "recommendation_score": 0.0,
                "semantic_reason": None,
                "recommendation_reason": None,
                "catalog_exact": False,
            },
        )

        row["content"] = content
        row["catalog_exact"] = True

    # --------------------------------------------------------
    # COLLECT SEMANTIC CANDIDATES
    # --------------------------------------------------------

    for result in semantic_results:
        content = result.get("content") or {}
        content_id = content.get("id")

        if content_id is None:
            continue

        row = candidates.setdefault(
            int(content_id),
            {
                "content": content,
                "semantic_score": 0.0,
                "recommendation_score": 0.0,
                "semantic_reason": None,
                "recommendation_reason": None,
                "catalog_exact": False,
            },
        )

        row["semantic_score"] = float(result.get("score", 0.0))
        row["semantic_reason"] = result.get("reason")

    # --------------------------------------------------------
    # COLLECT PERSONALIZED CANDIDATES
    # --------------------------------------------------------

    for result in recommendation_results:
        content = content_to_dict(result.get("content"))
        content_id = content.get("id")

        if content_id is None:
            continue

        row = candidates.setdefault(
            int(content_id),
            {
                "content": content,
                "semantic_score": 0.0,
                "recommendation_score": 0.0,
                "semantic_reason": None,
                "recommendation_reason": None,
                "catalog_exact": False,
            },
        )

        row["recommendation_score"] = float(result.get("score", 0.0))
        row["recommendation_reason"] = result.get("reason")

    exact_ranked: list[dict[str, Any]] = []
    similar_ranked: list[dict[str, Any]] = []

    requested = [
        normalize_genre(str(genre))
        for genre in intent.get("genres", [])
        if str(genre).strip()
    ]
    requested = list(dict.fromkeys(requested))
    requested_count = len(requested)

    exact_mode = effective_genre_match_mode(intent)

    # A copy used only for similar candidates. It preserves language,
    # exclusions and runtime rules while allowing partial genre overlap.
    similar_intent = dict(intent)
    similar_intent["allow_partial_genre_match"] = True
    similar_intent["genre_match_mode"] = "coverage"

    # --------------------------------------------------------
    # EVALUATE CANDIDATES
    # --------------------------------------------------------

    for content_id, candidate in candidates.items():
        content = candidate["content"]

        matched_genres, missing_genres, coverage = requested_genre_details(
            content,
            intent,
        )

        # First evaluate the exact interpretation.
        exact_allowed, exact_reasons = satisfies_hard_constraints(
            content,
            intent,
        )

        is_exact_genre_match = (
            not requested
            or (
                exact_mode == "any"
                and bool(matched_genres)
            )
            or (
                exact_mode == "all"
                and not missing_genres
            )
        )

        target_bucket = "exact" if (exact_allowed and is_exact_genre_match) else "similar"

        # If it is not exact, determine whether it is a legitimate similar
        # candidate. Similar candidates still MUST satisfy language,
        # exclusions, strict runtime/session budget and at least one genre.
        if target_bucket == "similar":
            if not requested or not matched_genres:
                rejected.append(
                    {
                        "content_id": content_id,
                        "title": content.get("title"),
                        "genres": content.get("genres"),
                        "runtime": content.get("duration_minutes"),
                        "reasons": exact_reasons or ["no requested genre overlap"],
                    }
                )
                continue

            similar_allowed, similar_reasons = satisfies_hard_constraints(
                content,
                similar_intent,
            )

            if not similar_allowed:
                rejected.append(
                    {
                        "content_id": content_id,
                        "title": content.get("title"),
                        "genres": content.get("genres"),
                        "runtime": content.get("duration_minutes"),
                        "reasons": similar_reasons,
                    }
                )
                continue

        verification_intent = intent if target_bucket == "exact" else similar_intent

        content_genre_check = verify_content_genres(
            content,
            verification_intent,
        )

        if not content_genre_check.get("allowed", True):
            rejected.append(
                {
                    "content_id": content_id,
                    "title": content.get("title"),
                    "genres": content.get("genres"),
                    "runtime": content.get("duration_minutes"),
                    "reasons": [
                        content_genre_check.get(
                            "reason",
                            "content-aware genre mismatch",
                        )
                    ],
                    "content_genre_verification": content_genre_check,
                }
            )
            continue

        # Recompute supported genre coverage after content verification.
        supported = {
            normalize_genre(str(genre))
            for genre in (
                content_genre_check.get("verified_supported", [])
                + content_genre_check.get("catalog_backed", [])
            )
        }

        # If the verifier has useful support information, use it to avoid
        # claiming an exact match when a suspicious catalog label failed.
        if requested and supported:
            verified_matched = [genre for genre in requested if genre in supported]
            verified_missing = [genre for genre in requested if genre not in supported]
            verified_coverage = len(verified_matched) / requested_count

            if target_bucket == "exact" and exact_mode == "all" and verified_missing:
                # Downgrade to Similar instead of silently presenting it as exact.
                target_bucket = "similar"
                matched_genres = verified_matched
                missing_genres = verified_missing
                coverage = verified_coverage

                partial_check = verify_content_genres(
                    content,
                    similar_intent,
                )

                if not partial_check.get("allowed", True):
                    rejected.append(
                        {
                            "content_id": content_id,
                            "title": content.get("title"),
                            "genres": content.get("genres"),
                            "runtime": content.get("duration_minutes"),
                            "reasons": [
                                partial_check.get(
                                    "reason",
                                    "content-aware genre mismatch",
                                )
                            ],
                            "content_genre_verification": partial_check,
                        }
                    )
                    continue

                content_genre_check = partial_check
            else:
                matched_genres = verified_matched
                missing_genres = verified_missing
                coverage = verified_coverage

        semantic = candidate["semantic_score"]
        recommendation = candidate["recommendation_score"]
        genre = coverage if requested else 0.0
        live_session = session_genre_score(content, session)
        session_budget_fit = session_budget_fit_score(content, intent)

        final_score = (
            0.52 * semantic
            + 0.25 * recommendation
            + 0.12 * genre
            + 0.08 * max(0.0, live_session)
            + 0.03 * max(0.0, session_budget_fit)
        )

        if live_session < 0:
            final_score += 0.06 * live_session

        final_score = max(0.0, min(0.99, final_score))

        reasons: list[str] = []

        if candidate["semantic_reason"]:
            reasons.append(candidate["semantic_reason"])

        if candidate["recommendation_reason"]:
            reasons.append(candidate["recommendation_reason"])

        if requested:
            if target_bucket == "exact":
                if exact_mode == "any":
                    reasons.append(
                        f"Matches {len(matched_genres)}/{requested_count} requested genres (OR query)"
                    )
                else:
                    reasons.append("Matches all requested genres")
            else:
                reasons.append(
                    f"Similar match: {len(matched_genres)}/{requested_count} requested genres"
                )

        verification_status = content_genre_check.get("status", "")
        verified_supported = content_genre_check.get("verified_supported", [])
        catalog_backed = content_genre_check.get("catalog_backed", [])

        if verified_supported:
            reasons.append(
                "Synopsis supports: "
                + ", ".join(
                    str(name).replace("sci-fi", "Sci-Fi").title()
                    for name in verified_supported
                )
            )
        elif verification_status == "CATALOG_BACKED" and catalog_backed:
            reasons.append(
                "Synopsis inconclusive; catalog-backed: "
                + ", ".join(
                    str(name).replace("sci-fi", "Sci-Fi").title()
                    for name in catalog_backed
                )
            )

        if intent.get("session_budget_minutes") is not None:
            if session_budget_fit >= 1.0:
                reasons.append(
                    f"Fits {intent['session_budget_minutes']}-minute viewing window"
                )
            else:
                reasons.append("Runtime unknown; viewing-window fallback")

        if live_session > 0.15:
            reasons.append("Fits your live session taste")

        row = {
            "content": content,
            "score": round(final_score, 4),
            "reason": "; ".join(dict.fromkeys(reasons)) or "Best valid agent match",
            "match_type": "EXACT" if target_bucket == "exact" else "SIMILAR",
            "matched_genres": matched_genres,
            "missing_genres": missing_genres,
            "genre_coverage": round(coverage, 4),
            "agent_signals": {
                "semantic": round(semantic, 4),
                "personalized_recommendation": round(recommendation, 4),
                "requested_genre": round(genre, 4),
                "live_session": round(live_session, 4),
                "session_budget_fit": round(session_budget_fit, 4),
                "content_genre_verification": content_genre_check,
                "final_score": round(final_score, 4),
            },
        }

        if target_bucket == "exact":
            exact_ranked.append(row)
        else:
            similar_ranked.append(row)

    # Exact matches are ranked by fit, then score.
    exact_ranked.sort(
        key=lambda row: (
            row.get("agent_signals", {}).get("session_budget_fit", 0.0)
            if intent.get("session_budget_minutes") is not None
            else 0.0,
            row["score"],
        ),
        reverse=True,
    )

    # Similar matches are ALWAYS ranked by genre coverage first.
    # This guarantees 2/3 appears above 1/3, regardless of semantic score.
    similar_ranked.sort(
        key=lambda row: (
            row.get("genre_coverage", 0.0),
            row.get("agent_signals", {}).get("session_budget_fit", 0.0)
            if intent.get("session_budget_minutes") is not None
            else 0.0,
            row["score"],
        ),
        reverse=True,
    )

    # Avoid weak padding. If we have enough strong partials, do not include
    # low-overlap alternatives.
    if requested_count >= 3 and similar_ranked:
        strong_floor = (requested_count - 1) / requested_count
        strong = [
            row for row in similar_ranked
            if row.get("genre_coverage", 0.0) >= strong_floor
        ]
        if len(strong) >= min(limit, 3):
            similar_ranked = strong

    return (
        exact_ranked[:limit],
        similar_ranked[:limit],
        rejected,
    )


# ============================================================
# MAIN AGENT
# ============================================================

async def run_agent(
    db: AsyncSession,
    query: str,
    user_id: int | None = None,
    limit: int = 10,
) -> dict[str, Any]:

    trace: list[
        dict[str, Any]
    ] = []

    # --------------------------------------------------------
    # STEP 1 — INTENT
    # --------------------------------------------------------

    intent = parse_intent(
        query
    )

    # NEXUS 6.7.0:
    # Natural multi-genre wording is an intersection. Explicit OR/either/
    # any-of wording remains disjunctive. The semantic retriever may still
    # gather broad candidates; the orchestrator separates exact vs similar.
    intent["genre_match_mode"] = effective_genre_match_mode(intent)

    trace.append(
        {
            "step":
                1,

            "tool":
                "intent_parser",

            "status":
                "success",

            "detail":
                (
                    "Detected "
                    f"{len(intent['hard_constraints'])} "
                    "hard constraints and "
                    f"{len(intent['soft_preferences'])} "
                    "soft preferences."
                ),
        }
    )

    # --------------------------------------------------------
    # STEP 2 — PROFILE
    # --------------------------------------------------------

    profile = (
        await get_user_profile(
            db,
            user_id,
        )
    )

    trace.append(
        {
            "step":
                2,

            "tool":
                "user_profile",

            "status":
                "success",

            "detail":
                (
                    "Loaded PostgreSQL user profile."
                    if profile[
                        "authenticated"
                    ]

                    else

                    "Anonymous request; profile skipped."
                ),
        }
    )

    # --------------------------------------------------------
    # STEP 3 — SESSION
    # --------------------------------------------------------

    session = (
        await get_session_context(
            user_id
        )
    )

    trace.append(
        {
            "step":
                3,

            "tool":
                "session_context",

            "status":
                "success",

            "detail":
                (
                    f"Loaded "
                    f"{session['event_count']} "
                    "live interaction events from Redis."
                    if session[
                        "available"
                    ]

                    else

                    "No live session context available."
                ),
        }
    )

    # --------------------------------------------------------
    # STEP 4 — CATALOG-FIRST EXACT DISCOVERY
    # --------------------------------------------------------

    exact_catalog_results = await discover_exact_catalog_candidates(
        db=db,
        intent=intent,
        limit=max(limit, 12),
    )

    trace.append(
        {
            "step": 4,
            "tool": "exact_catalog_discovery",
            "status": "success",
            "detail": (
                f"Found {len(exact_catalog_results)} exact catalog "
                "genre-combination candidates before semantic ranking."
            ),
        }
    )

    # --------------------------------------------------------
    # STEP 5 — SEMANTIC SEARCH
    # --------------------------------------------------------

    semantic = (
        await discovery_search(
            db=
                db,

            query=
                query,

            user_id=
                user_id,

            limit=
                max(
                    limit * 4,
                    40,
                ),

            source=
                "agent",

            language=
                (
                    intent.get(
                        "language"
                    )
                    or "all"
                ),
        )
    )

    semantic_results = (
        semantic.get(
            "results",
            [],
        )
    )

    trace.append(
        {
            "step":
                5,

            "tool":
                "semantic_search",

            "status":
                (
                    "success"
                    if semantic.get(
                        "semantic_ready"
                    )
                    else
                    "degraded"
                ),

            "detail":
                (
                    f"Retrieved "
                    f"{len(semantic_results)} "
                    "constraint-valid semantic candidates."
                ),
        }
    )

    # --------------------------------------------------------
    # STEP 6 — RECOMMENDER
    # --------------------------------------------------------

    recommendation_results: list[
        dict[str, Any]
    ] = []

    if user_id is not None:

        try:

            recommendation_results = (
                await nexus_recommendations(
                    db,
                    user_id,
                    limit=max(
                        limit * 4,
                        40,
                    ),
                )
            )

            trace.append(
                {
                    "step":
                        6,

                    "tool":
                        "hybrid_recommender",

                    "status":
                        "success",

                    "detail":
                        (
                            f"Retrieved "
                            f"{len(recommendation_results)} "
                            "personalized candidates."
                        ),
                }
            )

        except Exception as exc:

            trace.append(
                {
                    "step":
                        6,

                    "tool":
                        "hybrid_recommender",

                    "status":
                        "degraded",

                    "detail":
                        str(exc)[:160],
                }
            )

    else:

        trace.append(
            {
                "step":
                    6,

                "tool":
                    "hybrid_recommender",

                "status":
                    "skipped",

                "detail":
                    (
                        "Authentication required "
                        "for personalized recommendations."
                    ),
            }
        )

    # --------------------------------------------------------
    # STEP 7 — CONSTRAINT RERANK
    # --------------------------------------------------------

    (
        results,
        similar_results,
        rejected,
    ) = merge_candidates(
        semantic_results,
        recommendation_results,
        exact_catalog_results,
        intent,
        session,
        limit,
    )

    trace.append(
        {
            "step":
                7,

            "tool":
                "constraint_reranker",

            "status":
                "success",

            "detail":
                (
                    f"Returned {len(results)} exact candidates and "
                    f"{len(similar_results)} similar candidates; "
                    f"rejected {len(rejected)} invalid candidates."
                ),
        }
    )

    tools_used = [
        row[
            "tool"
        ]

        for row in trace

        if row[
            "status"
        ] in {
            "success",
            "degraded",
        }
    ]

    return {
        "query":
            query,

        "intent":
            intent,

        "tools_used":
            tools_used,

        "trace":
            trace,

        "context":
            {
                "profile":
                    profile,

                "session":
                    session,
            },

        "candidate_summary":
            {
                "exact_catalog_candidates":
                    len(
                        exact_catalog_results
                    ),

                "semantic_candidates":
                    len(
                        semantic_results
                    ),

                "recommendation_candidates":
                    len(
                        recommendation_results
                    ),

                "rejected_candidates":
                    len(
                        rejected
                    ),

                "returned_candidates":
                    len(
                        results
                    ),

                "similar_candidates":
                    len(
                        similar_results
                    ),
            },

        "results":
            results,

        "similar_results":
            similar_results,

        "exact_match_count":
            len(
                results
            ),

        "similar_match_count":
            len(
                similar_results
            ),

        "rejected_count":
            len(
                rejected
            ),

        "rejected":
            rejected[
                :30
            ],

        "agent_version":
            "6.8.0-catalog-first-exact-discovery",
    }