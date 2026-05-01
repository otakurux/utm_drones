"""events""" 
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from ..dependencies import get_ws_manager, get_redis_client, get_pubsub
from ...infrastructure.web.websocket_manager import WebSocketManager
from ...infrastructure.persistence.redis_client import RedisClient
from ...infrastructure.messaging.redis_pubsub import RedisPubSub


router = APIRouter(
    prefix="/ws",
    tags=["WebSocket"],
)


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    redis: RedisClient = Depends(get_redis_client),
):
    """
    Endpoint WebSocket para comunicación bidireccional en tiempo real.
    
    Protocolo de mensajes del cliente:
    - {"accion": "suscribir", "canales": ["posiciones", "alertas"]}
    - {"accion": "ping"}
    - {"accion": "estadisticas"}
    
    Mensajes del servidor:
    - PosicionActualizada: cada 500ms durante vuelos
    - Alerta: cuando se detectan conflictos
    - Eventos de dominio: DronDespego, EntregaCompletada, etc.
    - heartbeat: cada 30 segundos
    """
    await ws_manager.conectar(websocket)
    
    # Iniciar heartbeat en background
    heartbeat_task = asyncio.create_task(_heartbeat_loop(ws_manager, websocket))
    
    try:
        while True:
            # Recibir mensaje del cliente
            data = await websocket.receive_text()
            await ws_manager.manejar_mensaje_cliente(websocket, data)
            
    except WebSocketDisconnect:
        await ws_manager.desconectar(websocket)
    except Exception as e:
        print(f"Error en WebSocket: {e}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def _heartbeat_loop(
    ws_manager: WebSocketManager,
    websocket: WebSocket,
):
    """Envía heartbeat periódico para mantener la conexión activa."""
    from ...config import config
    import asyncio
    
    while True:
        try:
            await asyncio.sleep(config.WS_HEARTBEAT_INTERVAL)
            await ws_manager.enviar_heartbeat()
        except Exception:
            break


async def iniciar_reenvio_pubsub(
    pubsub: RedisPubSub,
    ws_manager: WebSocketManager,
):
    """
    Inicia el reenvío de mensajes de Redis Pub/Sub a WebSockets.
    Se ejecuta como tarea de background en el lifespan de FastAPI.
    """
    async def handler_posiciones(data: dict):
        await ws_manager.broadcast_posicion(data)
    
    async def handler_alertas(data: dict):
        await ws_manager.broadcast_alerta(data)
    
    async def handler_eventos(data: dict):
        await ws_manager.broadcast_evento(data.get("tipo", "Evento"), data)
    
    # Registrar handlers
    pubsub.registrar_handler(pubsub.CANAL_POSICIONES, handler_posiciones)
    pubsub.registrar_handler(pubsub.CANAL_ALERTAS, handler_alertas)
    pubsub.registrar_handler(pubsub.CANAL_EVENTOS, handler_eventos)
    pubsub.registrar_handler(pubsub.CANAL_DASHBOARD, handler_eventos)
    
    # Iniciar escucha
    await pubsub.escuchar()