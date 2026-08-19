"""API routers, one module per area."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import admin, me, reference

api_router = APIRouter()
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(reference.router)

__all__ = ["api_router"]
