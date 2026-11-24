from __future__ import annotations
import asyncio
from qdrant_client import models
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.content import Content
from app.services.semantic import embedder, qdrant, semantic_document

BATCH = 256


async def build_index() -> None:
    async with SessionLocal() as db:
        movies = list((await db.scalars(
            select(Content)
            .where(Content.catalog_source.in_(["movielens", "tmdb"]))
            .order_by(Content.id)
        )).all())
    if not movies:
        raise RuntimeError('Catalog is empty. Run MovieLens import and optionally TMDB Telugu import first.')

    client = qdrant()
    model = embedder()
    telugu_count = sum(1 for movie in movies if movie.original_language == 'te')
    print(f'Embedding {len(movies)} catalog movies ({telugu_count} Telugu) with {settings.embedding_model}...')

    first_vector = list(model.embed([semantic_document(movies[0])]))[0]
    size = len(first_vector)
    try:
        client.delete_collection(settings.qdrant_collection)
    except Exception:
        pass
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
    )

    for start in range(0, len(movies), BATCH):
        batch = movies[start:start + BATCH]
        docs = [semantic_document(item) for item in batch]
        vectors = [v.tolist() for v in model.embed(docs)]
        points = [models.PointStruct(
            id=item.id,
            vector=vector,
            payload={
                'content_id': item.id,
                'title': item.title,
                'original_title': item.original_title,
                'genres': item.genres,
                'tags': item.tags,
                'year': item.year,
                'language': item.original_language,
                'catalog_source': item.catalog_source,
                'tmdb_id': item.tmdb_id,
            },
        ) for item, vector in zip(batch, vectors)]
        client.upsert(collection_name=settings.qdrant_collection, points=points, wait=True)
        done = min(start + BATCH, len(movies))
        print(f'Indexed {done}/{len(movies)}')

    info = client.get_collection(settings.qdrant_collection)
    print({
        'collection': settings.qdrant_collection,
        'vectors': info.points_count,
        'telugu_movies': telugu_count,
        'embedding_model': settings.embedding_model,
    })
    print('Semantic index ready.')


def main():
    asyncio.run(build_index())


if __name__ == '__main__':
    main()
