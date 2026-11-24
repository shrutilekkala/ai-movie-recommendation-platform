from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.content import Content

from app.services.genre_validation import (
    serialize_genres,
    validate_movie_genres,
)


API_BASE = "https://api.themoviedb.org/3"

ACCENTS = [
    "neon",
    "violet",
    "cosmic",
    "sunset",
    "ember",
    "electric",
    "aqua",
    "rose",
    "lime",
    "ocean",
    "gold",
    "ice",
]


# ============================================================
# TMDB HTTP
# ============================================================

def _get(
    path: str,
    params: dict[str, Any] | None = None,
    retries: int = 3,
) -> dict[str, Any]:

    token = (
        settings
        .tmdb_bearer_token
        .strip()
    )

    if not token:

        raise RuntimeError(
            "TMDB_BEARER_TOKEN is missing."
        )

    query = urllib.parse.urlencode(
        params or {}
    )

    url = (
        f"{API_BASE}{path}"
        +
        (
            f"?{query}"
            if query
            else ""
        )
    )

    request = urllib.request.Request(
        url,
        headers={
            "Authorization":
                f"Bearer {token}",

            "accept":
                "application/json",

            "User-Agent":
                "NEXUS-Portfolio/6.8.6",
        },
    )

    last_error: Exception | None = None

    for attempt in range(
        1,
        retries + 1,
    ):

        try:

            with urllib.request.urlopen(
                request,
                timeout=45,
            ) as response:

                return json.loads(
                    response
                    .read()
                    .decode(
                        "utf-8"
                    )
                )

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
        ) as exc:

            last_error = exc

            if attempt >= retries:
                break

            delay = (
                attempt
                * 1.5
            )

            print(
                (
                    f"TMDB request failed "
                    f"for {path}. "
                    f"Retrying in "
                    f"{delay:.1f}s..."
                )
            )

            time.sleep(
                delay
            )

    raise RuntimeError(
        (
            f"TMDB request failed "
            f"for {path}: "
            f"{last_error}"
        )
    )


# ============================================================
# HELPERS
# ============================================================

def _year(
    value: str | None,
) -> int:

    if not value:
        return 0

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).year

    except ValueError:

        return 0


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:

    try:

        return int(
            value
            if value is not None
            else default
        )

    except (
        TypeError,
        ValueError,
    ):

        return default


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:

        return float(
            value
            if value is not None
            else default
        )

    except (
        TypeError,
        ValueError,
    ):

        return default


def _extract_tmdb_genres(
    details: dict[str, Any],
) -> list[str]:

    genres: list[str] = []

    for row in details.get(
        "genres",
        [],
    ):

        name = str(
            row.get(
                "name"
            )
            or ""
        ).strip()

        if name:

            genres.append(
                name
            )

    return genres


def _extract_tmdb_keywords(
    details: dict[str, Any],
) -> list[str]:

    payload = (
        details.get(
            "keywords"
        )
        or {}
    )

    rows = (
        payload.get(
            "keywords"
        )
        or payload.get(
            "results"
        )
        or []
    )

    values: list[str] = []
    seen: set[str] = set()

    for row in rows:

        name = str(
            row.get(
                "name"
            )
            or ""
        ).strip()

        normalized = (
            name.lower()
        )

        if (
            not name
            or normalized in seen
        ):
            continue

        seen.add(
            normalized
        )

        values.append(
            name
        )

    return values


# ============================================================
# WIKIDATA STRUCTURED GENRE FALLBACK — 6.8.6
# ============================================================

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_GENRE_ALIASES = {
    "science fiction film": ["Science Fiction"], "science fiction": ["Science Fiction"],
    "action film": ["Action"], "action comedy film": ["Action","Comedy"],
    "action thriller film": ["Action","Thriller"], "adventure film": ["Adventure"],
    "comedy film": ["Comedy"], "romantic comedy film": ["Romance","Comedy"],
    "crime film": ["Crime"], "crime thriller film": ["Crime","Thriller"],
    "drama film": ["Drama"], "fantasy film": ["Fantasy"], "horror film": ["Horror"],
    "mystery film": ["Mystery"], "romance film": ["Romance"], "romantic film": ["Romance"],
    "thriller film": ["Thriller"], "war film": ["War"], "western film": ["Western"],
    "animated film": ["Animation"], "musical film": ["Musical"], "film noir": ["Film-Noir"],
}

def _wikidata_api(params: dict[str, Any]) -> dict[str, Any]:
    try:
        req=Request(WIKIDATA_API+"?"+urlencode(params),headers={"User-Agent":"NEXUS-Portfolio/6.8.6"})
        with urlopen(req,timeout=12) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}

def _wikidata_qid_from_tmdb(tmdb_id: int) -> str | None:
    """
    Resolve a Wikidata item by the structured TMDB movie ID property P4947.

    The previous implementation used MediaWiki full-text search with
    haswbstatement:P4947=..., which can miss valid items because it depends
    on the search index. SPARQL queries the structured statement directly.
    """
    sparql = (
        'SELECT ?item WHERE { '
        f'?item wdt:P4947 "{int(tmdb_id)}" . '
        '} LIMIT 5'
    )

    try:
        req = Request(
            WIKIDATA_SPARQL + "?" + urlencode({
                "query": sparql,
                "format": "json",
            }),
            headers={
                "User-Agent": "NEXUS-Portfolio/6.8.6",
                "Accept": "application/sparql-results+json",
            },
        )

        with urlopen(req, timeout=15) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )
    except Exception:
        return None

    for row in (
        payload.get("results", {})
        .get("bindings", [])
        or []
    ):
        uri = (
            row.get("item", {})
            .get("value", "")
        )
        qid = uri.rsplit("/", 1)[-1].strip()

        if qid.startswith("Q"):
            return qid

    return None


def _map_wikidata_genre_labels(
    raw_labels: list[str],
) -> list[str]:

    generic = [
        ("science fiction", "Science Fiction"),
        ("action", "Action"),
        ("adventure", "Adventure"),
        ("comedy", "Comedy"),
        ("crime", "Crime"),
        ("drama", "Drama"),
        ("fantasy", "Fantasy"),
        ("horror", "Horror"),
        ("mystery", "Mystery"),
        ("romance", "Romance"),
        ("romantic", "Romance"),
        ("thriller", "Thriller"),
        ("historical", "Drama"),
        ("war film", "War"),
        ("western", "Western"),
        ("animated", "Animation"),
        ("musical", "Musical"),
    ]

    mapped: list[str] = []

    for label in raw_labels:
        low = str(label or "").strip().lower()

        if not low:
            continue

        values = (
            WIKIDATA_GENRE_ALIASES
            .get(low, [])
        )

        if not values:
            values = next(
                (
                    [canonical]
                    for token, canonical
                    in generic
                    if token in low
                ),
                [],
            )

        for value in values:
            if value not in mapped:
                mapped.append(value)

    return mapped


def _wikidata_genres_via_entity_api(
    qid: str,
) -> dict[str, Any]:
    """
    Fallback path that avoids the Wikidata Query Service entirely.
    """
    entity = _wikidata_api(
        {
            "action": "wbgetentities",
            "format": "json",
            "ids": qid,
            "props": "claims",
        }
    )

    claims = (
        entity.get("entities", {})
        .get(qid, {})
        .get("claims", {})
    )

    genre_qids: list[str] = []

    for claim in (
        claims.get("P136", [])
        or []
    ):
        try:
            genre_qid = (
                claim["mainsnak"]
                ["datavalue"]
                ["value"]
                ["id"]
            )
        except Exception:
            continue

        if genre_qid not in genre_qids:
            genre_qids.append(genre_qid)

    if not genre_qids:
        return {
            "qid": qid,
            "raw_labels": [],
            "genres": [],
            "source": "wikidata_entity_api",
        }

    labels_payload = _wikidata_api(
        {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(genre_qids),
            "props": "labels",
            "languages": "en",
        }
    )

    raw_labels: list[str] = []

    for genre_qid in genre_qids:
        label = (
            labels_payload
            .get("entities", {})
            .get(genre_qid, {})
            .get("labels", {})
            .get("en", {})
            .get("value", "")
            .strip()
        )

        if label and label not in raw_labels:
            raw_labels.append(label)

    return {
        "qid": qid,
        "raw_labels": raw_labels,
        "genres": _map_wikidata_genre_labels(raw_labels),
        "source": "wikidata_entity_api",
    }


def _wikidata_genres_for_tmdb(
    tmdb_id: int,
) -> dict[str, Any]:
    """
    6.8.6 resilient Wikidata lookup.

    1. Try the single SPARQL query up to 3 times.
    2. Retry transient 429/5xx failures with backoff.
    3. If Query Service still fails, resolve the QID and use the
       Wikidata entity API for P136 claims and labels.
    4. Return diagnostic source/error information instead of silently
       pretending the movie does not exist.
    """
    sparql = (
        'SELECT ?item ?genre ?genreLabel WHERE { '
        f'?item wdt:P4947 "{int(tmdb_id)}" . '
        'OPTIONAL { ?item wdt:P136 ?genre . } '
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } '
        '} LIMIT 50'
    )

    last_error: str | None = None

    for attempt in range(1, 4):
        try:
            req = Request(
                WIKIDATA_SPARQL + "?" + urlencode(
                    {
                        "query": sparql,
                        "format": "json",
                    }
                ),
                headers={
                    "User-Agent":
                        "NEXUS-Portfolio/6.8.6",
                    "Accept":
                        "application/sparql-results+json",
                },
            )

            with urlopen(
                req,
                timeout=20,
            ) as response:
                payload = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

            bindings = (
                payload.get("results", {})
                .get("bindings", [])
                or []
            )

            qid: str | None = None
            raw_labels: list[str] = []

            for row in bindings:
                item_uri = (
                    row.get("item", {})
                    .get("value", "")
                )

                candidate_qid = (
                    item_uri.rsplit("/", 1)[-1].strip()
                    if item_uri
                    else ""
                )

                if (
                    candidate_qid.startswith("Q")
                    and qid is None
                ):
                    qid = candidate_qid

                label = (
                    row.get("genreLabel", {})
                    .get("value", "")
                    .strip()
                )

                if (
                    label
                    and label not in raw_labels
                ):
                    raw_labels.append(label)

            if qid:
                return {
                    "qid": qid,
                    "raw_labels": raw_labels,
                    "genres":
                        _map_wikidata_genre_labels(
                            raw_labels
                        ),
                    "source":
                        "wikidata_sparql",
                    "error":
                        None,
                }

            last_error = (
                "SPARQL returned no matching QID"
            )

        except urllib.error.HTTPError as exc:
            last_error = (
                f"HTTPError {exc.code}: {exc.reason}"
            )

            # Retry only likely-transient responses.
            if (
                exc.code not in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }
            ):
                break

        except Exception as exc:
            last_error = (
                f"{type(exc).__name__}: {exc}"
            )

        if attempt < 3:
            delay = (
                (1.5 * attempt)
                + random.uniform(
                    0.1,
                    0.5,
                )
            )

            time.sleep(
                delay
            )

    # --------------------------------------------------------
    # FALLBACK — QID + ENTITY API
    # --------------------------------------------------------

    qid = _wikidata_qid_from_tmdb(
        tmdb_id
    )

    if qid:
        fallback = (
            _wikidata_genres_via_entity_api(
                qid
            )
        )

        fallback["error"] = (
            last_error
        )

        return fallback

    return {
        "qid": None,
        "raw_labels": [],
        "genres": [],
        "source": "wikidata_unavailable",
        "error": last_error,
    }

# ============================================================
# DISCOVERY
# ============================================================

def _discover_language(
    language_code: str,
    pages: int,
    start_year: int = 1950,
    end_year: int | None = None,
    historical_pages: int = 2,
    genre_pages: int = 1,
) -> tuple[
    list[dict[str, Any]],
    dict[int, str],
]:
    """
    Broad catalog discovery.

    TMDB /discover sorted only by popularity is strongly biased toward recent
    titles. NEXUS therefore combines three independent retrieval passes:
      1. global popularity for the requested original language,
      2. historical year windows, and
      3. per-genre discovery.

    This gives older and niche movies a path into PostgreSQL before the agent
    or Qdrant ever ranks them.
    """
    language_code = str(language_code or "te").strip().lower()
    current_year = datetime.utcnow().year
    end_year = min(int(end_year or current_year), current_year)
    start_year = max(1870, min(int(start_year), end_year))
    historical_pages = max(0, int(historical_pages))
    genre_pages = max(0, int(genre_pages))

    genre_payload = _get(
        "/genre/movie/list",
        {"language": "en-US"},
    )
    genre_map = {
        int(row["id"]): row["name"]
        for row in genre_payload.get("genres", [])
    }

    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add_results(payload: dict[str, Any]) -> int:
        added = 0
        for movie in payload.get("results", []):
            movie_id = _safe_int(movie.get("id"))
            if not movie_id or movie_id in seen:
                continue
            if str(movie.get("original_language") or "").lower() != language_code:
                continue
            seen.add(movie_id)
            rows.append(movie)
            added += 1
        return added

    # --------------------------------------------------------
    # PASS 1 — POPULARITY
    # --------------------------------------------------------
    for page in range(1, max(1, pages) + 1):
        payload = _get(
            "/discover/movie",
            {
                "include_adult": "false",
                "include_video": "false",
                "language": "en-US",
                "page": page,
                "sort_by": "popularity.desc",
                "with_original_language": language_code,
            },
        )
        add_results(payload)
        total_pages = _safe_int(payload.get("total_pages"), page)
        print(
            f"[popularity] {language_code} page {page}/"
            f"{min(total_pages, pages)} ({len(rows)} unique movies)"
        )
        if page >= total_pages:
            break

    # --------------------------------------------------------
    # PASS 2 — HISTORICAL YEAR WINDOWS
    # --------------------------------------------------------
    # A year-scoped pass prevents old titles from being buried behind
    # thousands of modern popularity-ranked movies.
    if historical_pages:
        for year in range(start_year, end_year + 1):
            year_added = 0
            for page in range(1, historical_pages + 1):
                payload = _get(
                    "/discover/movie",
                    {
                        "include_adult": "false",
                        "include_video": "false",
                        "language": "en-US",
                        "page": page,
                        "sort_by": "vote_count.desc",
                        "with_original_language": language_code,
                        "primary_release_year": year,
                    },
                )
                year_added += add_results(payload)
                total_pages = _safe_int(payload.get("total_pages"), page)
                if page >= total_pages:
                    break

            if year_added:
                print(
                    f"[history] {language_code} {year}: "
                    f"+{year_added} ({len(rows)} unique movies)"
                )

            time.sleep(0.03)

    # --------------------------------------------------------
    # PASS 3 — GENRE-SPECIFIC RECALL
    # --------------------------------------------------------
    # Genre passes improve coverage for sparse categories such as
    # Science Fiction, Horror, Animation, Documentary, etc.
    if genre_pages:
        for genre_id, genre_name in genre_map.items():
            genre_added = 0
            for page in range(1, genre_pages + 1):
                payload = _get(
                    "/discover/movie",
                    {
                        "include_adult": "false",
                        "include_video": "false",
                        "language": "en-US",
                        "page": page,
                        "sort_by": "vote_count.desc",
                        "with_original_language": language_code,
                        "with_genres": genre_id,
                    },
                )
                genre_added += add_results(payload)
                total_pages = _safe_int(payload.get("total_pages"), page)
                if page >= total_pages:
                    break

            if genre_added:
                print(
                    f"[genre] {language_code} {genre_name}: "
                    f"+{genre_added} ({len(rows)} unique movies)"
                )

            time.sleep(0.03)

    print(
        f"Discovery complete for {language_code}: "
        f"{len(rows)} unique movies."
    )
    return rows, genre_map


# ============================================================
# MOVIE DETAILS
# ============================================================

def _fetch_movie_details(
    tmdb_id: int,
) -> dict[str, Any]:

    return _get(
        f"/movie/{tmdb_id}",
        {
            "language":
                "en-US",

            # TMDB movie details supports append_to_response.
            # This avoids one additional HTTP request per movie.
            "append_to_response":
                "keywords",
        },
    )


def _fetch_details_safe(
    movie: dict[str, Any],
) -> dict[str, Any]:

    tmdb_id = _safe_int(
        movie.get(
            "id"
        )
    )

    if not tmdb_id:

        return {
            **movie,
            "_details": {},
            "_details_error":
                "missing tmdb id",
        }

    try:

        details = _fetch_movie_details(
            tmdb_id
        )

        return {
            **movie,
            "_details":
                details,
        }

    except Exception as exc:

        return {
            **movie,

            "_details":
                {},

            "_details_error":
                str(exc)[:180],
        }


def _fetch_all_details(
    movies: list[
        dict[str, Any]
    ],
) -> list[
    dict[str, Any]
]:

    enriched: list[
        dict[str, Any]
    ] = []

    total = len(
        movies
    )

    print(
        (
            f"Fetching details/runtime/genres "
            f"for {total} discovered movies..."
        )
    )

    for index, movie in enumerate(
        movies,
        start=1,
    ):

        enriched.append(
            _fetch_details_safe(
                movie
            )
        )

        if (
            index % 20 == 0
            or index == total
        ):

            print(
                (
                    f"Fetching details "
                    f"{index}/{total}"
                )
            )

        time.sleep(
            0.05
        )

    return enriched


# ============================================================
# IMPORT
# ============================================================

async def import_catalog(
    force: bool = False,
    pages: int | None = None,
    language: str = "te",
    start_year: int = 1950,
    end_year: int | None = None,
    historical_pages: int = 2,
    genre_pages: int = 1,
) -> None:

    language = str(language or "te").strip().lower()

    requested_pages = (
        pages
        or settings.tmdb_telugu_pages
    )

    movies, genre_map = (
        await asyncio.to_thread(
            _discover_language,
            language,
            requested_pages,
            start_year,
            end_year,
            historical_pages,
            genre_pages,
        )
    )

    if not movies:

        print(
            f"TMDB returned no movies for language={language}."
        )

        return

    movies = await asyncio.to_thread(
        _fetch_all_details,
        movies,
    )

    async with SessionLocal() as db:

        if force:

            print(
                (
                    f"Deleting existing TMDB-only rows "
                    f"for language={language}..."
                )
            )

            await db.execute(
                delete(
                    Content
                ).where(
                    Content.catalog_source
                    == "tmdb",

                    Content.original_language
                    == language,
                )
            )

            await db.commit()

        existing_rows = list(
            (
                await db.scalars(
                    select(
                        Content
                    ).where(
                        Content.tmdb_id
                        .is_not(
                            None
                        )
                    )
                )
            ).all()
        )

        by_tmdb = {
            int(
                row.tmdb_id
            ):
                row

            for row
            in existing_rows

            if row.tmdb_id
            is not None
        }

        inserted = 0
        enriched_existing = 0
        skipped = 0

        details_processed = 0
        details_failed = 0

        runtime_available = 0
        runtime_missing = 0

        genre_tmdb = 0
        genre_fallback = 0
        genre_overrides = 0
        genre_changed = 0
        genre_unknown = 0

        keywords_available = 0
        keywords_missing = 0
        genres_added_from_multi_signal = 0
        wikidata_checked = 0
        wikidata_matched = 0
        wikidata_genres_added = 0

        for movie in movies:

            tmdb_id = _safe_int(
                movie.get(
                    "id"
                )
            )

            if not tmdb_id:

                skipped += 1
                continue

            details = (
                movie.get(
                    "_details"
                )
                or {}
            )

            if details:

                details_processed += 1

            else:

                details_failed += 1

            tmdb_keywords = (
                _extract_tmdb_keywords(
                    details
                )
            )

            if tmdb_keywords:
                keywords_available += 1
            else:
                keywords_missing += 1

            # ------------------------------------------------
            # LANGUAGE
            # ------------------------------------------------

            original_language = str(
                details.get(
                    "original_language"
                )
                or movie.get(
                    "original_language"
                )
                or language
            ).strip().lower()

            if original_language != language:

                skipped += 1
                continue

            # ------------------------------------------------
            # GENRES
            # ------------------------------------------------

            raw_genres = (
                _extract_tmdb_genres(
                    details
                )
            )

            # Fallback only when /movie details
            # contains no genre list.
            if not raw_genres:

                raw_genres = [
                    genre_map.get(
                        _safe_int(
                            genre_id
                        ),
                        "",
                    )

                    for genre_id
                    in movie.get(
                        "genre_ids",
                        [],
                    )
                ]

                raw_genres = [
                    genre
                    for genre
                    in raw_genres
                    if genre
                ]

                if raw_genres:
                    genre_fallback += 1

            else:

                genre_tmdb += 1

            wikidata_info = {"qid": None, "raw_labels": [], "genres": []}
            if (not tmdb_keywords) or len(raw_genres) <= 2:
                wikidata_checked += 1
                wikidata_info = _wikidata_genres_for_tmdb(tmdb_id)
                if wikidata_info.get("qid"):
                    wikidata_matched += 1

            validation = (
                validate_movie_genres(
                    tmdb_id=
                        tmdb_id,

                    tmdb_genres=
                        raw_genres,

                    overview=
                        (
                            details.get("overview")
                            or movie.get("overview")
                            or ""
                        ),

                    keywords=
                        tmdb_keywords,

                    external_genres=
                        wikidata_info.get("genres", []),

                    title=
                        (
                            details.get("title")
                            or movie.get("title")
                            or ""
                        ),
                )
            )

            if (
                str(
                    validation[
                        "source"
                    ]
                ).startswith(
                    "manual_override"
                )
            ):

                genre_overrides += 1

            if validation[
                "changed"
            ]:

                genre_changed += 1

            genres_added_from_multi_signal += len(
                validation.get(
                    "added_genres",
                    []
                )
            )

            wikidata_genres_added += len(
                validation.get("external_added_genres", [])
            )

            primary, genres = (
                serialize_genres(
                    validation[
                        "genres"
                    ]
                )
            )

            if genres == "Other":

                genre_unknown += 1

            # ------------------------------------------------
            # RUNTIME
            # ------------------------------------------------

            runtime_raw = (
                details.get(
                    "runtime"
                )
            )

            runtime: int | None = None

            if runtime_raw is not None:

                parsed_runtime = (
                    _safe_int(
                        runtime_raw
                    )
                )

                if parsed_runtime > 0:

                    runtime = (
                        parsed_runtime
                    )

            if runtime is not None:

                runtime_available += 1

            else:

                runtime_missing += 1

            stored_runtime = (
                runtime
                if runtime is not None
                else 0
            )

            # ------------------------------------------------
            # GENERAL METADATA
            # ------------------------------------------------

            title = str(
                details.get(
                    "title"
                )
                or movie.get(
                    "title"
                )
                or movie.get(
                    "original_title"
                )
                or f"TMDB {tmdb_id}"
            ).strip()

            original_title = str(
                details.get(
                    "original_title"
                )
                or movie.get(
                    "original_title"
                )
                or title
            ).strip()

            overview = str(
                details.get(
                    "overview"
                )
                or movie.get(
                    "overview"
                )
                or ""
            ).strip()

            release_date = (
                details.get(
                    "release_date"
                )
                or movie.get(
                    "release_date"
                )
            )

            vote_average = (
                _safe_float(
                    details.get(
                        "vote_average"
                    )
                    if details
                    else movie.get(
                        "vote_average"
                    )
                )
            )

            vote_count = (
                _safe_int(
                    details.get(
                        "vote_count"
                    )
                    if details
                    else movie.get(
                        "vote_count"
                    )
                )
            )

            popularity = (
                _safe_float(
                    details.get(
                        "popularity"
                    )
                    if details
                    else movie.get(
                        "popularity"
                    )
                )
            )

            quality = min(
                0.99,
                max(
                    0.50,
                    (
                        vote_average
                        / 10.0
                        if vote_average
                        else 0.55
                    ),
                ),
            )

            poster_path = (
                details.get(
                    "poster_path"
                )
                or movie.get(
                    "poster_path"
                )
            )

            backdrop_path = (
                details.get(
                    "backdrop_path"
                )
                or movie.get(
                    "backdrop_path"
                )
            )

            # ------------------------------------------------
            # UPDATE EXISTING
            # ------------------------------------------------

            existing = (
                by_tmdb.get(
                    tmdb_id
                )
            )

            if existing:

                existing.title = (
                    title[:220]
                )

                existing.original_language = (
                    original_language
                )

                existing.original_title = (
                    original_title[:250]
                )

                existing.poster_path = (
                    poster_path
                )

                existing.backdrop_path = (
                    backdrop_path
                )

                existing.tmdb_popularity = (
                    popularity
                )

                existing.tmdb_vote_average = (
                    vote_average
                )

                existing.tmdb_vote_count = (
                    vote_count
                )

                existing.match_score = (
                    quality
                )

                existing.tags = (
                    f"{language}, {language} cinema, TMDB"
                    +
                    (
                        ", keywords: "
                        + ", ".join(
                            tmdb_keywords[:20]
                        )
                        if tmdb_keywords
                        else ""
                    )
                )

                existing.year = (
                    _year(
                        release_date
                    )
                )

                if runtime is not None:

                    existing.duration_minutes = (
                        runtime
                    )

                if overview:

                    existing.synopsis = (
                        overview
                    )

                # Genre validation is now authoritative.
                existing.genre = (
                    primary[:120]
                )

                existing.genres = (
                    genres
                )

                enriched_existing += 1

                continue

            # ------------------------------------------------
            # INSERT NEW
            # ------------------------------------------------

            synopsis = (
                overview
                or
                (
                    "Telugu movie from TMDB. "
                    f"Genres: "
                    f"{genres.replace('|', ', ')}."
                )
            )

            row = Content(
                title=
                    title[:220],

                synopsis=
                    synopsis,

                genre=
                    primary[:120],

                genres=
                    genres,

                tags=
                    (
                        f"{language}, {language} cinema, TMDB"
                        +
                        (
                            ", keywords: "
                            + ", ".join(
                                tmdb_keywords[:20]
                            )
                            if tmdb_keywords
                            else ""
                        )
                    ),

                content_type=
                    "Movie",

                year=
                    _year(
                        release_date
                    ),

                duration_minutes=
                    stored_runtime,

                match_score=
                    quality,

                maturity_rating=
                    "NR",

                accent=
                    ACCENTS[
                        tmdb_id
                        %
                        len(
                            ACCENTS
                        )
                    ],

                featured=
                    False,

                catalog_source=
                    "tmdb",

                tmdb_id=
                    tmdb_id,

                original_language=
                    original_language,

                original_title=
                    original_title[:250],

                poster_path=
                    poster_path,

                backdrop_path=
                    backdrop_path,

                tmdb_popularity=
                    popularity,

                tmdb_vote_average=
                    vote_average,

                tmdb_vote_count=
                    vote_count,
            )

            db.add(
                row
            )

            by_tmdb[
                tmdb_id
            ] = row

            inserted += 1

        await db.commit()

    # ========================================================
    # SUMMARY
    # ========================================================

    print()

    print(
        json.dumps(
            {
                "source":
                    "TMDB",

                "language":
                    language,

                "fetched":
                    len(
                        movies
                    ),

                "inserted":
                    inserted,

                "enriched_existing":
                    enriched_existing,

                "skipped":
                    skipped,

                "pages_requested":
                    requested_pages,

                "historical_start_year":
                    start_year,

                "historical_end_year":
                    end_year or datetime.utcnow().year,

                "historical_pages_per_year":
                    historical_pages,

                "genre_pages":
                    genre_pages,

                "details_processed":
                    details_processed,

                "details_failed":
                    details_failed,

                "runtime_available":
                    runtime_available,

                "runtime_missing":
                    runtime_missing,

                "genre_tmdb":
                    genre_tmdb,

                "genre_discover_fallback":
                    genre_fallback,

                "genre_manual_overrides":
                    genre_overrides,

                "genre_changed":
                    genre_changed,

                "genre_unknown":
                    genre_unknown,

                "keywords_available":
                    keywords_available,

                "keywords_missing":
                    keywords_missing,

                "genres_added_from_multi_signal":
                    genres_added_from_multi_signal,

                "wikidata_checked":
                    wikidata_checked,

                "wikidata_matched":
                    wikidata_matched,

                "wikidata_genres_added":
                    wikidata_genres_added,
            },
            indent=2,
        )
    )

    print()

    print(
        f"Multi-source catalog import complete for language={language}."
    )

    print(
        "Rebuild Qdrant:"
    )

    print(
        (
            "docker compose exec backend "
            "python -m app.scripts.build_semantic_index"
        )
    )


# ============================================================
# CLI
# ============================================================

def main() -> None:

    if not (
        settings
        .tmdb_bearer_token
        .strip()
    ):

        print(
            "TMDB_BEARER_TOKEN is missing."
        )

        raise SystemExit(
            2
        )

    parser = argparse.ArgumentParser(
        description=(
            "Import, enrich, and validate "
            "movie metadata from TMDB with broad historical discovery."
        )
    )

    parser.add_argument(
        "--force",
        action=
            "store_true",

        help=
            (
                "Delete TMDB-only rows for the selected language "
                "before rebuilding that language catalog."
            ),
    )

    parser.add_argument(
        "--pages",
        type=
            int,

        default=
            None,

        help=
            (
                "Number of TMDB Discover "
                "pages to process."
            ),
    )

    parser.add_argument(
        "--language",
        type=str,
        default="te",
        help="TMDB original-language code, e.g. te, en, hi, ta, ko, ja.",
    )

    parser.add_argument(
        "--start-year",
        type=int,
        default=1950,
        help="First release year included in historical backfill.",
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Last release year included in historical backfill.",
    )

    parser.add_argument(
        "--historical-pages",
        type=int,
        default=2,
        help="TMDB pages fetched for each year. Use 0 to disable.",
    )

    parser.add_argument(
        "--genre-pages",
        type=int,
        default=1,
        help="TMDB pages fetched for each genre. Use 0 to disable.",
    )

    args = (
        parser.parse_args()
    )

    asyncio.run(
        import_catalog(
            force=args.force,
            pages=args.pages,
            language=args.language,
            start_year=args.start_year,
            end_year=args.end_year,
            historical_pages=args.historical_pages,
            genre_pages=args.genre_pages,
        )
    )


if __name__ == "__main__":
    main()