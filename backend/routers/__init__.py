from .auth import router as auth_router
from .bili import router as bili_router
from .local import router as local_router
from .play import router as play_router
from .system import router as system_router
from .theme import router as theme_router
from .download import router as download_router

__all__ = [
    "auth_router",
    "bili_router",
    "local_router",
    "play_router",
    "system_router",
    "theme_router",
    "download_router",
]
