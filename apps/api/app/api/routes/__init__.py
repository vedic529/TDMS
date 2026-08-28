"""API routers, one module per area."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    allocation,
    me,
    reference,
    rolling_timetable,
    students,
    suggestions,
    trainers,
)

api_router = APIRouter()
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(reference.router)
api_router.include_router(rolling_timetable.router)
api_router.include_router(allocation.router)
api_router.include_router(students.router)
api_router.include_router(suggestions.router)
api_router.include_router(trainers.router)

__all__ = ["api_router"]
