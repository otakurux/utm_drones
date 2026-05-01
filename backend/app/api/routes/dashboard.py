"""dashboard"""
from fastapi import APIRouter, Depends, HTTPException, status

from ..dto import (
    EstadisticasDTO,
    EstadoFlotaDTO,
    AlertaDTO,
    RespuestaExitosaDTO,
)
from ..dependencies import (
    get_redis_client,
    get_servicio_flota,
    get_servicio_priorizacion,
    get_vuelo_repo,
    verificar_mongodb_conectado,
    verificar_redis_conectado,
)
from ...infrastructure.persistence.redis_client import RedisClient
from ...domain.services.servicio_gestion_flota import ServicioGestionFlota
from ...domain.services.servicio_priorizacion_entregas import ServicioPriorizacionEntregas
from ...infrastructure.persistence.mongodb_repo import VueloRepository


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(verificar_mongodb_conectado), Depends(verificar_redis_conectado)],
)


@router.get(
    "/estadisticas",
    response_model=RespuestaExitosaDTO,
    summary="Obtener estadísticas generales del sistema"
)
async def obtener_estadisticas(
    servicio_flota: ServicioGestionFlota = Depends(get_servicio_flota),
    servicio_priorizacion: ServicioPriorizacionEntregas = Depends(get_servicio_priorizacion),
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    redis: RedisClient = Depends(get_redis_client),
):
    """
    Obtiene estadísticas consolidadas para el dashboard:
    - Estado de la flota
    - Alertas operativas
    - Entregas pendientes
    - Vuelos activos
    """
    # Estado de flota
    estado_flota = servicio_flota.obtener_estado_flota()
    
    # Alertas
    alertas_raw = servicio_flota.obtener_alertas()
    alertas = [AlertaDTO(**a) for a in alertas_raw]
    
    # Entregas pendientes
    entregas_pendientes = servicio_priorizacion.cantidad_pendientes()
    hay_criticas = servicio_priorizacion.hay_entregas_criticas()
    
    # Vuelos activos
    vuelos_activos = await vuelo_repo.listar_activos()
    
    # Posiciones en tiempo real
    posiciones = await redis.obtener_posiciones_todas()
    
    estadisticas = EstadisticasDTO(
        estado_flota=EstadoFlotaDTO(
            total_drones=estado_flota.total_drones,
            disponibles=estado_flota.disponibles,
            en_vuelo=estado_flota.en_vuelo,
            cargando=estado_flota.cargando,
            mantenimiento=estado_flota.mantenimiento,
            bateria_promedio=round(estado_flota.bateria_promedio, 1),
            entregas_activas=estado_flota.entregas_activas,
        ),
        alertas=alertas,
        entregas_pendientes=entregas_pendientes,
        entregas_criticas=hay_criticas,
        vuelos_activos=len(vuelos_activos),
    )
    
    return RespuestaExitosaDTO(
        mensaje="Estadísticas obtenidas",
        data={
            "estadisticas": estadisticas.model_dump(),
            "posiciones_tiempo_real": posiciones,
            "vuelos_activos": [v.to_dict() for v in vuelos_activos],
        }
    )


@router.get(
    "/flota",
    response_model=RespuestaExitosaDTO,
    summary="Obtener estado completo de la flota"
)
async def obtener_estado_flota(
    servicio_flota: ServicioGestionFlota = Depends(get_servicio_flota),
):
    """Obtiene el estado detallado de todos los drones."""
    estado = servicio_flota.obtener_estado_flota()
    
    return RespuestaExitosaDTO(
        mensaje="Estado de flota obtenido",
        data={
            "resumen": {
                "total": estado.total_drones,
                "disponibles": estado.disponibles,
                "en_vuelo": estado.en_vuelo,
                "cargando": estado.cargando,
                "mantenimiento": estado.mantenimiento,
                "bateria_promedio": round(estado.bateria_promedio, 1),
            },
            "drones": [
                d.to_dict() for d in servicio_flota._drones.values()
            ]
        }
    )


@router.get(
    "/alertas",
    response_model=RespuestaExitosaDTO,
    summary="Obtener alertas operativas activas"
)
async def obtener_alertas(
    servicio_flota: ServicioGestionFlota = Depends(get_servicio_flota),
):
    """Obtiene todas las alertas operativas activas."""
    alertas = servicio_flota.obtener_alertas()
    
    return RespuestaExitosaDTO(
        mensaje="Alertas obtenidas",
        data={"alertas": alertas, "total": len(alertas)}
    )


@router.get(
    "/cola-entregas",
    response_model=RespuestaExitosaDTO,
    summary="Obtener cola de priorización de entregas"
)
async def obtener_cola_entregas(
    servicio_priorizacion: ServicioPriorizacionEntregas = Depends(get_servicio_priorizacion),
):
    """Obtiene la cola de entregas ordenada por prioridad."""
    cola = servicio_priorizacion.obtener_cola_ordenada()
    
    return RespuestaExitosaDTO(
        mensaje="Cola de entregas obtenida",
        data={
            "total_pendientes": len(cola),
            "entregas": cola,
        }
    )


@router.get(
    "/trafico-activo",
    response_model=RespuestaExitosaDTO,
    summary="Obtener tráfico aéreo activo"
)
async def obtener_trafico_activo(
    redis: RedisClient = Depends(get_redis_client),
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
):
    """Obtiene información del tráfico aéreo actual."""
    vuelos_activos_ids = await redis.obtener_vuelos_activos()
    posiciones = await redis.obtener_posiciones_todas()
    rutas = await redis.obtener_todas_rutas_activas()
    
    return RespuestaExitosaDTO(
        mensaje="Tráfico activo obtenido",
        data={
            "vuelos_activos": vuelos_activos_ids,
            "posiciones_drones": posiciones,
            "rutas_activas": rutas,
            "total_drones_en_aire": len(posiciones),
        }
    )