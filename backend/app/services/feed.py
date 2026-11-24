from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.content import Content
from app.schemas.content import FeedSection, HomeFeed


async def build_home_feed(session: AsyncSession) -> HomeFeed:
    real_count = await session.scalar(
        select(func.count()).select_from(Content).where(Content.catalog_source == "movielens")
    )
    telugu_count = await session.scalar(
        select(func.count()).select_from(Content).where(Content.original_language == "te")
    )

    if real_count and real_count > 0:
        base = list((await session.scalars(
            select(Content)
            .where(Content.catalog_source == "movielens", Content.rating_count >= 20)
            .order_by(desc(Content.rating_count), desc(Content.avg_rating))
            .limit(180)
        )).all())
        if not base:
            base = list((await session.scalars(
                select(Content).where(Content.catalog_source == "movielens")
                .order_by(desc(Content.rating_count)).limit(180)
            )).all())

        hero = base[0]
        top = base[:12]
        highly_rated = sorted(base, key=lambda x: ((x.avg_rating or 0.0), x.rating_count), reverse=True)[:12]
        sci_fi = [x for x in base if any(g in x.genres for g in ["Sci-Fi", "Mystery", "Thriller", "Adventure"])][:12]
        comedy = [x for x in base if "Comedy" in x.genres][:12]

        sections = [
            FeedSection(key="real-popular", title="Popular in Real MovieLens Data", items=top),
            FeedSection(key="real-rated", title="Highly Rated by Real Viewers", items=highly_rated),
            FeedSection(key="future-now", title="Sci-Fi, Mystery & Adventure", items=sci_fi),
            FeedSection(key="comedy", title="Comedy Picks", items=comedy),
        ]

        if telugu_count and telugu_count > 0:
            telugu = list((await session.scalars(
                select(Content)
                .where(Content.original_language == "te")
                .order_by(desc(Content.tmdb_popularity), desc(Content.tmdb_vote_count))
                .limit(12)
            )).all())
            if telugu:
                sections.insert(0, FeedSection(key="telugu", title="తెలుగు • Telugu Cinema", items=telugu))

        return HomeFeed(hero=hero, sections=sections)

    hero = await session.scalar(select(Content).where(Content.featured.is_(True)).limit(1))
    if hero is None:
        hero = await session.scalar(select(Content).order_by(desc(Content.match_score)).limit(1))
    if hero is None:
        raise RuntimeError("Content catalog is empty")

    all_items = list((await session.scalars(select(Content).order_by(desc(Content.match_score)))).all())
    trending = all_items[:8]
    sci_fi = [item for item in all_items if item.genre in {"Sci-Fi", "Tech Thriller", "Mystery"}][:8]
    quick = [item for item in all_items if item.duration_minutes <= 45][:8]

    return HomeFeed(
        hero=hero,
        sections=[
            FeedSection(key="top-picks", title="Top Picks for You", items=trending),
            FeedSection(key="future-now", title="Future, Mystery & Tech", items=sci_fi),
            FeedSection(key="quick-watch", title="Quick Watch", items=quick),
        ],
    )
