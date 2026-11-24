from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import re
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, func, insert, select

from app.db.session import SessionLocal
from app.models.content import Content
from app.models.recommendation import MovieLensRating

DATASET_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
ARTIFACT_PATH = Path("/app/artifacts/movielens_model.json")
ACCENTS = ["neon", "violet", "cosmic", "sunset", "ember", "electric", "aqua", "rose", "lime", "ocean", "gold", "ice"]


def chunks(items: list[dict], size: int = 2000) -> Iterable[list[dict]]:
    for idx in range(0, len(items), size):
        yield items[idx: idx + size]


def parse_year(title: str) -> int:
    match = re.search(r"\((\d{4})\)\s*$", title)
    return int(match.group(1)) if match else 0


def clean_title(title: str) -> str:
    return re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()


def download_dataset() -> bytes:
    print(f"Downloading official MovieLens latest-small from {DATASET_URL}")
    req = urllib.request.Request(DATASET_URL, headers={"User-Agent": "NEXUS-Portfolio/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def read_zip_csv(blob: bytes, filename: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        with archive.open(f"ml-latest-small/{filename}") as raw:
            return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")))


from app.ml.collaborative import train_model


async def import_data(force: bool = False) -> None:
    async with SessionLocal() as db:
        existing = await db.scalar(select(func.count()).select_from(MovieLensRating))
        if existing and existing > 0 and not force:
            print(f"MovieLens is already loaded ({existing} ratings). Use --force to rebuild.")
            return

    blob = await asyncio.to_thread(download_dataset)
    movies_rows = read_zip_csv(blob, "movies.csv")
    ratings_rows = read_zip_csv(blob, "ratings.csv")
    links_rows = read_zip_csv(blob, "links.csv")
    tags_rows = read_zip_csv(blob, "tags.csv")
    links = {int(row["movieId"]): row for row in links_rows}

    tags_by_movie: dict[int, list[str]] = defaultdict(list)
    for row in tags_rows:
        tag = (row.get("tag") or "").strip()
        if tag and tag.lower() not in {t.lower() for t in tags_by_movie[int(row["movieId"])]}:
            tags_by_movie[int(row["movieId"])].append(tag)

    rating_stats: dict[int, list[float]] = defaultdict(list)
    for row in ratings_rows:
        rating_stats[int(row["movieId"])].append(float(row["rating"]))

    async with SessionLocal() as db:
        if force:
            await db.execute(delete(MovieLensRating))
            await db.execute(delete(Content).where(Content.catalog_source == "movielens"))
            await db.commit()

        content_rows = []
        for idx, row in enumerate(movies_rows):
            mlid = int(row["movieId"])
            genres = row["genres"] if row["genres"] != "(no genres listed)" else "Other"
            primary = genres.split("|")[0]
            values = rating_stats.get(mlid, [])
            avg = sum(values) / len(values) if values else None
            count = len(values)
            link = links.get(mlid, {})
            title = clean_title(row["title"])
            year = parse_year(row["title"])
            quality = 0.5 if avg is None else min(0.99, max(0.50, avg / 5.0))
            content_rows.append({
                "title": title[:220],
                "synopsis": f"Real MovieLens catalog title. Genres: {genres.replace('|', ', ')}. NEXUS will enrich plot, runtime and artwork in the multimodal metadata phase.",
                "genre": primary[:120],
                "genres": genres,
                "tags": ", ".join(tags_by_movie.get(mlid, [])[:30]),
                "content_type": "Movie",
                "year": year,
                "duration_minutes": 110,
                "match_score": quality,
                "maturity_rating": "NR",
                "accent": ACCENTS[mlid % len(ACCENTS)],
                "featured": False,
                "catalog_source": "movielens",
                "movielens_id": mlid,
                "imdb_id": link.get("imdbId") or None,
                "tmdb_id": int(link["tmdbId"]) if link.get("tmdbId") else None,
                "original_language": "en",
                "original_title": title[:250],
                "poster_path": None,
                "backdrop_path": None,
                "avg_rating": round(avg, 4) if avg is not None else None,
                "rating_count": count,
            })

        print(f"Importing {len(content_rows)} MovieLens movies into PostgreSQL...")
        for batch in chunks(content_rows, 1500):
            await db.execute(insert(Content), batch)
        await db.commit()

        db_movies = list((await db.execute(
            select(Content.id, Content.movielens_id).where(Content.catalog_source == "movielens")
        )).all())
        content_by_ml = {mlid: content_id for content_id, mlid in db_movies if mlid is not None}

        rating_inserts = []
        for row in ratings_rows:
            content_id = content_by_ml.get(int(row["movieId"]))
            if content_id is None:
                continue
            rating_inserts.append({
                "movielens_user_id": int(row["userId"]),
                "content_id": content_id,
                "rating": float(row["rating"]),
                "timestamp": int(row["timestamp"]),
            })
        print(f"Importing {len(rating_inserts)} real ratings...")
        for batch in chunks(rating_inserts, 5000):
            await db.execute(insert(MovieLensRating), batch)
        await db.commit()

    print("Training popularity, collaborative, content-based, hybrid and learned-hybrid recommenders...")
    artifact = await asyncio.to_thread(train_model, ratings_rows, movies_rows)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact), encoding="utf-8")
    print(json.dumps({"stats": artifact["stats"], "winner": artifact.get("winner"), "learned_weights": artifact.get("learned_weights"), "model_comparison": artifact.get("model_comparison")}, indent=2))
    print("MovieLens import + model training complete.")
    print("Next build semantic discovery: docker compose exec backend python -m app.scripts.build_semantic_index")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import MovieLens latest-small and train the NEXUS recommender.")
    parser.add_argument("--force", action="store_true", help="Delete and rebuild existing MovieLens catalog/ratings.")
    args = parser.parse_args()
    asyncio.run(import_data(force=args.force))


if __name__ == "__main__":
    main()
