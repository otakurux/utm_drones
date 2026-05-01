"""vuelos""" 
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..dto import (
    VueloCreateDTO,
    VueloResponseDTO,
    RespuestaExitosaDTO,
    WaypointDTO,
)
from ..dependencies import (
    get_vuelo_repo,
    get_dron_repo,
    get_entrega_repo,
    get_redis_client,
    get_pubsub,
    verificar_mongodb_conectado,
)
from ...domain.entities.vuelo import Vuelo
from ...domain.aggregates.vuelo_agg import AgregadoVuelo
from ...domain.enums.estados import EstadoVuelo
from ...infrastructure.persistence.mongodb_repo import (
    VueloRepository,
    DronRepository,
    EntregaRepository,
)
from ...infrastructure.persistence.redis_client import RedisClient
from ...infrastructure.messaging.redis_pubsub import RedisPubSub


router = APIRouter(
    prefix="/vuelos",
    tags=["Vuelos"],
    dependencies=[Depends(verificar_mongodb_conectado)],
)


@router.post(
    "",
    response_model=RespuestaExitosaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo vuelo"
)
async def crear_vuelo(
    dto: VueloCreateDTO,
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    dron_repo: DronRepository = Depends(get_dron_repo),
    entrega_repo: EntregaRepository = Depends(get_entrega_repo),
):
    """Crea un nuevo vuelo manualmente."""
    # Verificar dron existe
    dron = await dron_repo.obtener_por_id(UUID(dto.dron_id))
    if not dron:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron no encontrado"
        )
    
    # Verificar entrega existe
    entrega = await entrega_repo.obtener_por_id(UUID(dto.entrega_id))
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )
    
    # Crear vuelo
    vuelo = Vuelo()
    vuelo.asignar_dron(dron.id)
    vuelo.asignar_entrega(entrega.id)
    
    # Crear plan de vuelo básico desde waypoints
    from ...domain.value_objects.plan_vuelo import PlanDeVuelo, Waypoint
    plan = PlanDeVuelo()
    for i, wp_dto in enumerate(dto.waypoints):
        wp = Waypoint(
            orden=i,
            latitud=wp_dto.latitud,
            longitud=wp_dto.longitud,
            altitud=wp_dto.altitud,
        )
        plan.agregar_waypoint(wp)
    
    vuelo.establecer_plan(plan)
    await vuelo_repo.guardar(vuelo)
    
    return RespuestaExitosaDTO(
        mensaje="Vuelo creado exitosamente",
        data=vuelo.to_dict()
    )


@router.get(
    "",
    response_model=List[VueloResponseDTO],
    summary="Listar vuelos"
)
async def listar_vuelos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    estado: Optional[str] = Query(None, pattern="^(planificado|en_ruta|completado|cancelado|emergencia)$"),
    repo: VueloRepository = Depends(get_vuelo_repo),
):
    """Lista vuelos con filtros opcionales."""
    if estado:
        vuelos = await repo.listar_por_estado(EstadoVuelo(estado))
    else:
        vuelos = await repo.listar_todos(skip, limit)
    
    return [VueloResponseDTO(**v.to_dict()) for v in vuelos]


@router.get(
    "/activos",
    response_model=List[VueloResponseDTO],
    summary="Listar vuelos activos (EN_RUTA)"
)
async def listar_vuelos_activos(
    repo: VueloRepository = Depends(get_vuelo_repo),
):
    """Lista todos los vuelos actualmente en ruta."""
    vuelos = await repo.listar_activos()
    return [VueloResponseDTO(**v.to_dict()) for v in vuelos]


@router.get(
    "/{vuelo_id}",
    response_model=VueloResponseDTO,
    summary="Obtener vuelo por ID"
)
async def obtener_vuelo(
    vuelo_id: str,
    repo: VueloRepository = Depends(get_vuelo_repo),
):
    """Obtiene información detallada de un vuelo."""
    vuelo = await repo.obtener_por_id(UUID(vuelo_id))
    if not vuelo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vuelo no encontrado"
        )
    return VueloResponseDTO(**vuelo.to_dict())


@router.post(
    "/{vuelo_id}/despegar",
    response_model=RespuestaExitosaDTO,
    summary="Iniciar vuelo (despegue)"
)
async def despegar_vuelo(
    vuelo_id: str,
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    dron_repo: DronRepository = Depends(get_dron_repo),
    entrega_repo: EntregaRepository = Depends(get_entrega_repo),
    redis: RedisClient = Depends(get_redis_client),
    pubsub: RedisPubSub = Depends(get_pubsub),
):
    """
    Inicia el vuelo: el dron despega y la entrega pasa a EN_RUTA.
    Genera evento DronDespego vía Redis Pub/Sub.
    """
    vuelo = await vuelo_repo.obtener_por_id(UUID(vuelo_id))
    if not vuelo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vuelo no encontrado"
        )
    
    if vuelo.estado != EstadoVuelo.PLANIFICADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El vuelo no está planificado. Estado: {vuelo.estado.value}"
        )
    
    # Obtener dron
    dron = await dron_repo.obtener_por_id(vuelo.dron_id)
    if not dron:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron asignado no encontrado"
        )
    
    # Iniciar vuelo y despegar dron
    try:
        evento_despego = dron.despegar(vuelo.id)
        vuelo.iniciar()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Actualizar entrega
    entrega = await entrega_repo.obtener_por_id(vuelo.entrega_id)
    if entrega:
        entrega.iniciar_entrega()
        await entrega_repo.guardar(entrega)
    
    # Guardar cambios
    await dron_repo.guardar(dron)
    await vuelo_repo.guardar(vuelo)
    
    # Registrar en Redis
    await redis.registrar_vuelo_activo(vuelo.id)
    await redis.actualizar_estado(dron.id, "en_vuelo")
    
    # Publicar evento
    await pubsub.publicar_evento(evento_despego)
    
    return RespuestaExitosaDTO(
        mensaje="Vuelo iniciado exitosamente",
        data={
            "vuelo": vuelo.to_dict(),
            "evento": evento_despego.to_dict(),
        }
    )


@router.post(
    "/{vuelo_id}/cancelar",
    response_model=RespuestaExitosaDTO,
    summary="Cancelar vuelo"
)
async def cancelar_vuelo(
    vuelo_id: str,
    motivo: str = Query(default="Cancelado por operador"),
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    dron_repo: DronRepository = Depends(get_dron_repo),
    redis: RedisClient = Depends(get_redis_client),
):
    """Cancela un vuelo planificado o en curso."""
    vuelo = await vuelo_repo.obtener_por_id(UUID(vuelo_id))
    if not vuelo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vuelo no encontrado"
        )
    
    if vuelo.estado in [EstadoVuelo.COMPLETADO, EstadoVuelo.CANCELADO]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El vuelo ya está {vuelo.estado.value}"
        )
    
    vuelo.cancelar(motivo)
    await vuelo_repo.guardar(vuelo)
    
    # Liberar dron
    if vuelo.dron_id:
        dron = await dron_repo.obtener_por_id(vuelo.dron_id)
        if dron:
            dron.estado = __import__('backend.app.domain.enums.estados', fromlist=['EstadoDron']).EstadoDron.DISPONIBLE
            await dron_repo.guardar(dron)
            await redis.actualizar_estado(dron.id, "disponible")
    
    await redis.remover_vuelo_activo(vuelo.id)
    await redis.eliminar_ruta(vuelo.id)
    
    return RespuestaExitosaDTO(
        mensaje="Vuelo cancelado",
        data=vuelo.to_dict()
    )


@router.post(
    "/{vuelo_id}/emergencia",
    response_model=RespuestaExitosaDTO,
    summary="Activar modo emergencia"
)
async def emergencia_vuelo(
    vuelo_id: str,
    motivo: str = Query(..., description="Motivo de la emergencia"),
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    dron_repo: DronRepository = Depends(get_dron_repo),
    redis: RedisClient = Depends(get_redis_client),
    pubsub: RedisPubSub = Depends(get_pubsub),
):
    """Activa modo emergencia para aterrizaje forzado."""
    vuelo = await vuelo_repo.obtener_por_id(UUID(vuelo_id))
    if not vuelo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vuelo no encontrado"
        )
    
    vuelo.emergencia()
    await vuelo_repo.guardar(vuelo)
    
    # Publicar alerta crítica
    await pubsub.publicar_alerta({
        "tipo": "EMERGENCIA",
        "vuelo_id": str(vuelo.id),
        "dron_id": str(vuelo.dron_id) if vuelo.dron_id else None,
        "motivo": motivo,
        "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
    })
    
    return RespuestaExitosaDTO(
        mensaje="Modo emergencia activado",
        data={"vuelo": vuelo.to_dict(), "motivo": motivo}
    )