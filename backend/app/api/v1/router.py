"""Aggregates all /api/v1 sub-routers.

Each phase that adds an API surface (auth, documents, search, chat, agents, ...)
registers its router here — this file is the single place that shows the full
API surface at a glance.
"""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.agents import router as agents_router
from app.api.v1.auth import router as auth_router
from app.api.v1.collections import router as collections_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.search import router as search_router
from app.api.v1.tools import router as tools_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(organizations_router, prefix="/organizations", tags=["organizations"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(collections_router, prefix="/collections", tags=["collections"])
api_router.include_router(search_router, prefix="/search", tags=["search"])
api_router.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(tools_router, prefix="/tools", tags=["tools"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
