from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.content import Content
from app.schemas.content import ContentOut, HomeFeed
from app.services.feed import build_home_feed

router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=list[ContentOut])
async def list_content(
    q: str | None = Query(default=None, min_length=1, max_length=100),
    genre: str | None = None,
    session: AsyncSession = Depends(get_db),
) -> list[Content]:
    statement = select(Content).order_by(Content.match_score.desc())
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(Content.title.ilike(pattern), Content.synopsis.ilike(pattern), Content.genre.ilike(pattern)))
    if genre:
        statement = statement.where(Content.genre == genre)
    return list((await session.scalars(statement)).all())


@router.get("/feed", response_model=HomeFeed)
async def home_feed(session: AsyncSession = Depends(get_db)) -> HomeFeed:
    return await build_home_feed(session)


@router.get("/{content_id}", response_model=ContentOut)
async def get_content(content_id: int, session: AsyncSession = Depends(get_db)) -> Content:
    item = await session.get(Content, content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return item
