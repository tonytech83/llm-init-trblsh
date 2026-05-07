from fastapi import APIRouter

from app.api.endpoints import alerts, ui

router = APIRouter()

router.include_router(ui.router)
router.include_router(alerts.router)
