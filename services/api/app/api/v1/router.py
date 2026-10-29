from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(ai_router)
router.include_router(auth_router)
