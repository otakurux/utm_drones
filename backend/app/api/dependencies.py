from fastapi import Request, HTTPException, status

from ..infrastructure.persistence.mongodb_repo import (
    MongoDBConnection,
    DronRepository,
    VueloRepository,
    EntregaRepository,
    ZonaRepository,
    EventoAuditoriaRepository,
)
from ..infrastructure.persistence.redis_client import RedisClient
from ..infrastructure.messaging.redis_pubsub import RedisPubSub
from ..infrastructure.web.websocket_manager import WebSocketManager


# ============================================================
# Dependencias de Repositorios
# ============================================================

async def get_dron_repo(request: Request) -> DronRepository:
    return request.app.state.dron_repo

async def get_vuelo_repo(request: Request) -> VueloRepository:
    return request.app.state.vuelo_repo

async def get_entrega_repo(request: Request) -> EntregaRepository:
    return request.app.state.entrega_repo

async def get_zona_repo(request: Request) -> ZonaRepository:
    return request.app.state.zona_repo

async def get_evento_repo(request: Request) -> EventoAuditoriaRepository:
    return request.app.state.evento_repo


# ============================================================
# Dependencias de Infraestructura
# ============================================================

async def get_redis_client(request: Request) -> RedisClient:
    return request.app.state.redis_client

async def get_pubsub(request: Request) -> RedisPubSub:
    return request.app.state.pubsub

async def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager


# ============================================================
# Dependencias de Servicios de Dominio
# ============================================================

async def get_servicio_planificacion(request: Request):
    return request.app.state.servicio_planificacion

async def get_servicio_priorizacion(request: Request):
    return request.app.state.servicio_priorizacion

async def get_servicio_conflictos(request: Request):
    return request.app.state.servicio_conflictos

async def get_servicio_flota(request: Request):
    return request.app.state.servicio_flota


# ============================================================
# Verificaciones
# ============================================================

async def verificar_mongodb_conectado(request: Request):
    """Verifica que MongoDB esté conectado antes de procesar la petición."""
    conn = MongoDBConnection()
    if conn._db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible"
        )

async def verificar_redis_conectado(request: Request):
    """Verifica que Redis esté conectado antes de procesar la petición."""
    redis = request.app.state.redis_client
    if redis._client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Caché en tiempo real no disponible"
        )