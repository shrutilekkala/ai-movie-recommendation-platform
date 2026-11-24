from app.api.routes.agent import router as agent_router
from fastapi import APIRouter
from app.api.routes.content import router as content_router
from app.api.routes.auth import router as auth_router
from app.api.routes.user_actions import router as user_actions_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.realtime import router as realtime_router
from app.api.routes.discovery import router as discovery_router

api_router = APIRouter()
api_router.include_router(content_router)
api_router.include_router(auth_router)
api_router.include_router(user_actions_router)
api_router.include_router(recommendations_router)

api_router.include_router(realtime_router)
api_router.include_router(discovery_router)
api_router.include_router(agent_router)
