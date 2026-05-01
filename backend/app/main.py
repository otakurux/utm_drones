"""main""" 
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .api.routes import (
    drones_router,
    entregas_router,
    vuelos_router,
    zonas_router,
    dashboard_router,
)
from .api.websocket.events import websocket_router, iniciar_reenvio_pubsub
from .infrastructure.persistence.mongodb_repo import (
    MongoDBConnection,
    DronRepository,
    VueloRepository,
    EntregaRepository,
    ZonaRepository,
    EventoAuditoriaRepository,
)
from .infrastructure.persistence.redis_client import RedisClient
from .infrastructure.messaging.redis_pubsub import RedisPubSub
from .infrastructure.web.websocket_manager import WebSocketManager
from .domain.services.servicio_planificacion_rutas import ServicioPlanificacionRutas
from .domain.services.servicio_priorizacion_entregas import ServicioPriorizacionEntregas
from .domain.services.servicio_deteccion_conflictos import ServicioDeteccionConflictos
from .domain.services.servicio_gestion_flota import ServicioGestionFlota


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de la aplicación:
    - Conexión a bases de datos al iniciar
    - Carga de servicios de dominio
    - Tareas de background (Pub/Sub, detección de conflictos)
    - Cierre ordenado al finalizar
    """
    print(f"🚀 Iniciando {config.APP_NAME}...")
    
    # ============================================================
    # CONEXIÓN A BASES DE DATOS
    # ============================================================
    
    # MongoDB
    mongo_conn = MongoDBConnection()
    await mongo_conn.connect()
    print("✅ MongoDB conectado")
    
    # Redis
    redis_client = RedisClient()
    await redis_client.connect()
    print("✅ Redis conectado")
    
    # ============================================================
    # REPOSITORIOS
    # ============================================================
    
    dron_repo = DronRepository()
    vuelo_repo = VueloRepository()
    entrega_repo = EntregaRepository()
    zona_repo = ZonaRepository()
    evento_repo = EventoAuditoriaRepository()
    
    # ============================================================
    # SERVICIOS DE DOMINIO
    # ============================================================
    
    # Cargar zonas restringidas activas
    zonas = await zona_repo.listar_activas()
    
    servicio_planificacion = ServicioPlanificacionRutas(zonas_restringidas=zonas)
    servicio_priorizacion = ServicioPriorizacionEntregas()
    servicio_conflictos = ServicioDeteccionConflictos()
    servicio_flota = ServicioGestionFlota()
    
    # Cargar drones existentes en el servicio de flota
    drones = await dron_repo.listar_todos()
    for dron in drones:
        servicio_flota.registrar_dron(dron)
    
    # ============================================================
    # MENSAJERÍA Y WEBSOCKETS
    # ============================================================
    
    pubsub = RedisPubSub(redis_client)
    await pubsub.connect()
    print("✅ Redis Pub/Sub conectado")
    
    ws_manager = WebSocketManager()
    
    # ============================================================
    # ALMACENAR EN ESTADO DE LA APP
    # ============================================================
    
    app.state.mongo_conn = mongo_conn
    app.state.redis_client = redis_client
    app.state.dron_repo = dron_repo
    app.state.vuelo_repo = vuelo_repo
    app.state.entrega_repo = entrega_repo
    app.state.zona_repo = zona_repo
    app.state.evento_repo = evento_repo
    app.state.servicio_planificacion = servicio_planificacion
    app.state.servicio_priorizacion = servicio_priorizacion
    app.state.servicio_conflictos = servicio_conflictos
    app.state.servicio_flota = servicio_flota
    app.state.pubsub = pubsub
    app.state.ws_manager = ws_manager
    
    # ============================================================
    # TAREAS DE BACKGROUND
    # ============================================================
    
    # Tarea 1: Reenvío Pub/Sub -> WebSockets
    task_pubsub = asyncio.create_task(iniciar_reenvio_pubsub(pubsub, ws_manager))
    
    # Tarea 2: Detección de conflictos cada 500ms
    task_conflictos = asyncio.create_task(_loop_deteccion_conflictos(
        servicio_conflictos, redis_client, pubsub
    ))
    
    # Tarea 3: Verificación de estado de flota cada 30s
    task_flota = asyncio.create_task(_loop_verificacion_flota(
        servicio_flota, dron_repo, pubsub
    ))
    
    # Tarea 4: Actualización de scores de prioridad cada 60s
    task_prioridad = asyncio.create_task(_loop_actualizar_prioridades(
        servicio_priorizacion
    ))
    
    print("✅ Tareas de background iniciadas")
    print(f"🎯 {config.APP_NAME} listo en http://localhost:8000")
    
    yield  # La aplicación está corriendo
    
    # ============================================================
    # SHUTDOWN
    # ============================================================
    
    print("🛑 Cerrando aplicación...")
    
    # Cancelar tareas
    for task in [task_pubsub, task_conflictos, task_flota, task_prioridad]:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Cerrar conexiones
    await pubsub.disconnect()
    await redis_client.disconnect()
    await mongo_conn.disconnect()
    
    print("✅ Aplicación cerrada correctamente")


# ============================================================
# TAREAS DE BACKGROUND
# ============================================================

async def _loop_deteccion_conflictos(
    servicio: ServicioDeteccionConflictos,
    redis: RedisClient,
    pubsub: RedisPubSub,
):
    """Loop cada 500ms para detección de conflictos."""
    while True:
        try:
            # Actualizar rutas activas en el servicio
            rutas = await redis.obtener_todas_rutas_activas()
            # (Aquí se actualizaría el servicio con las rutas)
            
            # Detectar conflictos
            conflictos = servicio.detectar_conflictos()
            
            for conflicto in conflictos:
                await pubsub.publicar_alerta(conflicto.to_dict())
            
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error en detección de conflictos: {e}")
            await asyncio.sleep(1)


async def _loop_verificacion_flota(
    servicio: ServicioGestionFlota,
    repo: DronRepository,
    pubsub: RedisPubSub,
):
    """Loop cada 30s para verificación de estado de flota."""
    while True:
        try:
            eventos = servicio.verificar_estado_drones()
            
            for evento in eventos:
                # Persistir evento
                await pubsub.publicar_evento(evento)
                # Guardar dron actualizado
                dron = servicio.obtener_dron(evento.dron_id)
                if dron:
                    await repo.guardar(dron)
            
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error en verificación de flota: {e}")
            await asyncio.sleep(30)


async def _loop_actualizar_prioridades(
    servicio: ServicioPriorizacionEntregas,
):
    """Loop cada 60s para actualizar scores de prioridad."""
    while True:
        try:
            servicio.actualizar_scores()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error en actualización de prioridades: {e}")
            await asyncio.sleep(60)


# ============================================================
# APLICACIÓN FASTAPI
# ============================================================

app = FastAPI(
    title="UTM Drones - Sistema de Gestión de Tráfico Aéreo",
    description="""
    Sistema de Gestión de Tráfico Aéreo (UTM) para drones urbanos.
    
    ## Funcionalidades
    
    * **Drones**: Registro y gestión de flota
    * **Entregas**: Solicitudes con priorización automática
    * **Vuelos**: Planificación y monitoreo en tiempo real
    * **Zonas**: Gestión de espacios restringidos
    * **Dashboard**: Estadísticas y alertas operativas
    * **WebSocket**: Actualizaciones en tiempo real
    
    ## Tecnologías
    
    * FastAPI + Python 3.11+
    * MongoDB 7.x (persistencia)
    * Redis 7.x (tiempo real)
    * WebSockets (comunicación bidireccional)
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ROUTERS
# ============================================================

app.include_router(drones_router)
app.include_router(entregas_router)
app.include_router(vuelos_router)
app.include_router(zonas_router)
app.include_router(dashboard_router)
app.include_router(websocket_router)


# ============================================================
# ENDPOINTS DE SALUD
# ============================================================

@app.get("/", tags=["Salud"])
async def root():
    """Endpoint raíz."""
    return {
        "nombre": config.APP_NAME,
        "version": "1.0.0",
        "status": "operativo",
        "documentacion": "/docs",
    }


@app.get("/health", tags=["Salud"])
async def health_check():
    """Verificación de salud del sistema."""
    mongo_ok = MongoDBConnection()._db is not None
    redis_ok = app.state.redis_client._client is not None if hasattr(app.state, 'redis_client') else False
    
    status_code = 200 if (mongo_ok and redis_ok) else 503
    
    return {
        "status": "saludable" if (mongo_ok and redis_ok) else "degradado",
        "servicios": {
            "mongodb": "conectado" if mongo_ok else "desconectado",
            "redis": "conectado" if redis_ok else "desconectado",
        },
        "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
    }