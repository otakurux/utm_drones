from .routes import (
    drones_router,
    entregas_router,
    vuelos_router,
    zonas_router,
    dashboard_router,
)
from .websocket.events import router as websocket_router

__all__ = [
    "drones_router",
    "entregas_router",
    "vuelos_router",
    "zonas_router",
    "dashboard_router",
    "websocket_router",
]