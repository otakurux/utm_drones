from .drones import router as drones_router
from .entregas import router as entregas_router
from .vuelos import router as vuelos_router
from .zonas import router as zonas_router
from .dashboard import router as dashboard_router

__all__ = [
    "drones_router",
    "entregas_router",
    "vuelos_router",
    "zonas_router",
    "dashboard_router",
]