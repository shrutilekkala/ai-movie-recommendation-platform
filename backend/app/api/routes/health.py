from fastapi import APIRouter
from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.config import settings
import redis.asyncio as redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "nexus-api"}


@router.get("/ready")
async def ready() -> dict:
    checks = {"postgres": False, "redis": False}
    async with SessionLocal() as session:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = True

    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        checks["redis"] = bool(await client.ping())
    finally:
        await client.aclose()
    return {"status": "ready" if all(checks.values()) else "degraded", "checks": checks}
