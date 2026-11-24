from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.recommendation import RecommendationOut, RecommendationStatus
from app.services.recommender import (
    movielens_user_recommendations,
    nexus_recommendations,
    status_payload,
)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/status", response_model=RecommendationStatus)
async def recommendation_status() -> dict:
    return status_payload()


@router.get("/me", response_model=list[RecommendationOut])
async def my_recommendations(
    limit: int = Query(default=12, ge=1, le=30),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await nexus_recommendations(db, user.id, limit=limit)


@router.get("/movielens/{user_id}", response_model=list[RecommendationOut])
async def real_movielens_user_recommendations(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    return await movielens_user_recommendations(db, user_id, limit=limit)
