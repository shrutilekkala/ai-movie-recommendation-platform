from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.content import Content

DEMO_CONTENT = [
    {"title":"Neon Horizon","synopsis":"A systems engineer discovers a signal hidden inside a city-scale recommendation network and must decide whether to expose the intelligence behind it.","genre":"Sci-Fi","content_type":"Movie","year":2026,"duration_minutes":126,"match_score":0.98,"maturity_rating":"PG-13","accent":"neon","featured":True},
    {"title":"Midnight Protocol","synopsis":"An elite incident-response team races through one night to stop an autonomous attack from spreading across a global streaming platform.","genre":"Tech Thriller","content_type":"Series","year":2026,"duration_minutes":48,"match_score":0.96,"maturity_rating":"TV-14","accent":"violet","featured":False},
    {"title":"Orbit Zero","synopsis":"Six strangers wake aboard a research station with fragmented memories and an AI that refuses to reveal why Earth has gone silent.","genre":"Sci-Fi","content_type":"Series","year":2025,"duration_minutes":52,"match_score":0.94,"maturity_rating":"TV-14","accent":"cosmic","featured":False},
    {"title":"Laugh Track 404","synopsis":"A chaotic comedy about four friends building a startup whose AI assistant becomes accidentally famous before their product launches.","genre":"Comedy","content_type":"Series","year":2026,"duration_minutes":24,"match_score":0.91,"maturity_rating":"TV-14","accent":"sunset","featured":False},
    {"title":"The Last Frame","synopsis":"A documentary editor finds a single unexplained frame in decades of archived footage and follows it into a forgotten cultural mystery.","genre":"Mystery","content_type":"Movie","year":2024,"duration_minutes":108,"match_score":0.89,"maturity_rating":"PG-13","accent":"ember","featured":False},
    {"title":"Velocity","synopsis":"Underdog racers build an electric prototype for an illegal cross-country competition where every route is predicted by machine learning.","genre":"Action","content_type":"Movie","year":2025,"duration_minutes":117,"match_score":0.87,"maturity_rating":"PG-13","accent":"electric","featured":False},
    {"title":"Signal / Noise","synopsis":"Creators, engineers and musicians explain how recommendation algorithms reshape culture, discovery and the meaning of going viral.","genre":"Documentary","content_type":"Movie","year":2026,"duration_minutes":92,"match_score":0.93,"maturity_rating":"PG","accent":"aqua","featured":False},
    {"title":"Afterglow","synopsis":"A quiet anthology of near-future stories about memory, relationships and the digital traces people leave behind.","genre":"Drama","content_type":"Series","year":2025,"duration_minutes":43,"match_score":0.86,"maturity_rating":"TV-14","accent":"rose","featured":False},
    {"title":"Parallel Play","synopsis":"Competitive gamers are recruited into a mixed-reality tournament where teamwork matters more than reflexes.","genre":"Adventure","content_type":"Series","year":2026,"duration_minutes":38,"match_score":0.90,"maturity_rating":"TV-PG","accent":"lime","featured":False},
    {"title":"Deep Current","synopsis":"Marine researchers use autonomous robots to map an unexplored trench and uncover a biological system unlike anything on record.","genre":"Documentary","content_type":"Movie","year":2025,"duration_minutes":84,"match_score":0.85,"maturity_rating":"PG","accent":"ocean","featured":False},
    {"title":"One More Minute","synopsis":"A collection of sharp, one-minute stories where every character has exactly sixty seconds to make a life-changing choice.","genre":"Shorts","content_type":"Shorts","year":2026,"duration_minutes":1,"match_score":0.88,"maturity_rating":"TV-PG","accent":"gold","featured":False},
    {"title":"Ghost Cache","synopsis":"A developer tracing corrupted cache entries realizes each one predicts an event that has not happened yet.","genre":"Mystery","content_type":"Movie","year":2026,"duration_minutes":101,"match_score":0.92,"maturity_rating":"PG-13","accent":"ice","featured":False},
]


async def seed_content(session: AsyncSession) -> None:
    count = await session.scalar(select(func.count()).select_from(Content))
    if count and count > 0:
        return
    session.add_all([Content(**item) for item in DEMO_CONTENT])
    await session.commit()

async def seed_demo_user(session: AsyncSession) -> None:
    from sqlalchemy import select
    from app.models.user import User
    from app.core.security import hash_password
    if (await session.execute(select(User).where(User.email == 'demo@nexus.ai'))).scalar_one_or_none():
        return
    session.add(User(email='demo@nexus.ai', display_name='Demo Viewer', password_hash=hash_password('nexus123'), favorite_genres='Sci-Fi,Comedy,Mystery'))
    await session.commit()
