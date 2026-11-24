from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.db.base import Base
from app.db.seed import seed_content, seed_demo_user
from app.db.session import SessionLocal, engine
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_content(session)
        await seed_demo_user(session)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.5.0",
    description="NEXUS Phase 5 backend: semantic discovery, Qdrant vector retrieval, MovieLens recommendations and real-time personalization.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root() -> dict:
    return {"name": "NEXUS API", "docs": "/docs", "health": "/health"}
