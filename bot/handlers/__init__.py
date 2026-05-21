from aiogram import Router

from .menu import router as menu_router
from .workout import router as workout_router
from .tracking import router as tracking_router


def build_router() -> Router:
    root = Router()
    root.include_router(menu_router)
    root.include_router(workout_router)
    root.include_router(tracking_router)
    return root
