from __future__ import annotations
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.content import Content
from app.models.user import AuthSession, User
from app.services.semantic import discovery_search, semantic_status

router = APIRouter(prefix='/discovery', tags=['semantic-discovery'])

async def optional_user_id(authorization: str | None, db: AsyncSession) -> int | None:
    if not authorization or not authorization.startswith('Bearer '):
        return None
    token = authorization.removeprefix('Bearer ').strip()
    row = await db.execute(select(User.id).join(AuthSession, AuthSession.user_id == User.id).where(AuthSession.token == token))
    return row.scalar_one_or_none()

@router.get('/status')
async def status():
    return await semantic_status()

@router.get('/catalog-status')
async def catalog_status(db: AsyncSession = Depends(get_db)):
    total = int(await db.scalar(select(func.count()).select_from(Content)) or 0)
    movielens = int(await db.scalar(select(func.count()).select_from(Content).where(Content.catalog_source == 'movielens')) or 0)
    tmdb = int(await db.scalar(select(func.count()).select_from(Content).where(Content.catalog_source == 'tmdb')) or 0)
    telugu = int(await db.scalar(select(func.count()).select_from(Content).where(Content.original_language == 'te')) or 0)
    return {'total': total, 'movielens': movielens, 'tmdb': tmdb, 'telugu': telugu}

@router.get('/search')
async def search(
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=12, ge=1, le=30),
    source: str = Query(default='text', pattern='^(text|voice)$'),
    language: str = Query(default='all', pattern='^(all|en|te)$'),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    user_id = await optional_user_id(authorization, db)
    return await discovery_search(db, q, user_id=user_id, limit=limit, source=source, language=language)

@router.get('/debug')
async def debug_search(
    q: str = Query(min_length=2, max_length=300),
    limit: int = Query(default=12, ge=1, le=30),
    language: str = Query(default='all', pattern='^(all|en|te)$'),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    user_id = await optional_user_id(authorization, db)
    return await discovery_search(db, q, user_id=user_id, limit=limit, debug=True, source='debug', language=language)
