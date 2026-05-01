"""entregas""" 
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..dto import (
    EntregaCreateDTO,
    EntregaResponseDTO,
    RespuestaExitosaDTO,
)
from ..dependencies import (
    get_entrega_repo,
    get_dron_repo,
    get_vuelo_repo,
    get_redis_client,
    get_servicio_priorizacion,
    get_servicio_planificacion,
    get_servicio_flota,
    verificar_mongodb_conectado,
)
from ...domain.entities.entrega import Entrega
from ...domain.aggregates.pedido_agg import AgregadoPedido
from ...domain.value_objects.direccion import DireccionDestino
from ...domain.enums.estados import EstadoEntrega, TipoEntrega
from ...infrastructure.persistence.mongodb_repo import (
    EntregaRepository,
    DronRepository,
    VueloRepository,
)
from ...infrastructure.persistence.redis_client import RedisClient
from ...domain.services.servicio_priorizacion_entregas import ServicioPriorizacionEntregas
from ...domain.services.servicio_planificacion_rutas import ServicioPlanificacionRutas
from ...domain.services.servicio_gestion_flota import ServicioGestionFlota


router = APIRouter(
    prefix="/entregas",
    tags=["Entregas"],
    dependencies=[Depends(verificar_mongodb_conectado)],
)


@router.post(
    "",
    response_model=RespuestaExitosaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nueva solicitud de entrega"
)
async def crear_entrega(
    dto: EntregaCreateDTO,
    repo: EntregaRepository = Depends(get_entrega_repo),
    servicio_priorizacion: ServicioPriorizacionEntregas = Depends(get_servicio_priorizacion),
):
    """Crea una nueva entrega y la encola para priorización."""
    # Verificar número de pedido único
    existente = await repo.obtener_por_pedido(dto.numero_pedido)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una entrega con número de pedido {dto.numero_pedido}"
        )
    
    # Crear agregado Pedido
    agregado = AgregadoPedido.crear_pedido(
        numero_pedido=dto.numero_pedido,
        cliente_id=UUID(dto.cliente_id) if dto.cliente_id else None,
        tipo=dto.tipo,
        peso_kg=dto.paquete.peso_kg,
        origen=DireccionDestino(
            latitud=dto.direccion_origen.latitud,
            longitud=dto.direccion_origen.longitud,
            altitud=dto.direccion_origen.altitud,
            instrucciones=dto.direccion_origen.instrucciones,
        ),
        destino=DireccionDestino(
            latitud=dto.direccion_destino.latitud,
            longitud=dto.direccion_destino.longitud,
            altitud=dto.direccion_destino.altitud,
            instrucciones=dto.direccion_destino.instrucciones,
        ),
        dimensiones=dto.paquete.dimensiones_cm,
        fragil=dto.paquete.fragil,
    )
    
    entrega = agregado.raiz
    await repo.guardar(entrega)
    
    # Encolar para priorización
    servicio_priorizacion.encolar_entrega(entrega)
    
    return RespuestaExitosaDTO(
        mensaje="Entrega creada y encolada para priorización",
        data=entrega.to_dict()
    )


@router.get(
    "",
    response_model=List[EntregaResponseDTO],
    summary="Listar entregas"
)
async def listar_entregas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    estado: Optional[str] = Query(None, pattern="^(pendiente|asignada|en_ruta|entregado|fallido)$"),
    tipo: Optional[str] = Query(None, pattern="^(medicina|alimentos|farmacia|general)$"),
    repo: EntregaRepository = Depends(get_entrega_repo),
):
    """Lista entregas con filtros opcionales."""
    if estado:
        entregas = await repo.listar_por_estado(EstadoEntrega(estado))
    else:
        # Lista todas con paginación simple
        from ...infrastructure.persistence.mongodb_repo import MongoDBConnection
        conn = MongoDBConnection()
        cursor = conn.db.entregas.find().skip(skip).limit(limit)
        entregas = [repo._from_document(doc) async for doc in cursor]
    
    if tipo:
        entregas = [e for e in entregas if e.tipo.value == tipo]
    
    return [EntregaResponseDTO(**e.to_dict()) for e in entregas]


@router.get(
    "/pendientes",
    response_model=List[EntregaResponseDTO],
    summary="Listar entregas pendientes ordenadas por prioridad"
)
async def listar_pendientes(
    repo: EntregaRepository = Depends(get_entrega_repo),
):
    """Lista entregas pendientes ordenadas por prioridad descendente."""
    entregas = await repo.listar_pendientes()
    return [EntregaResponseDTO(**e.to_dict()) for e in entregas]


@router.get(
    "/criticas",
    response_model=List[EntregaResponseDTO],
    summary="Listar entregas críticas (medicina)"
)
async def listar_criticas(
    repo: EntregaRepository = Depends(get_entrega_repo),
):
    """Lista entregas de medicina pendientes o en ruta."""
    entregas = await repo.listar_criticas()
    return [EntregaResponseDTO(**e.to_dict()) for e in entregas]


@router.get(
    "/{entrega_id}",
    response_model=EntregaResponseDTO,
    summary="Obtener entrega por ID"
)
async def obtener_entrega(
    entrega_id: str,
    repo: EntregaRepository = Depends(get_entrega_repo),
):
    """Obtiene información detallada de una entrega."""
    entrega = await repo.obtener_por_id(UUID(entrega_id))
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )
    return EntregaResponseDTO(**entrega.to_dict())


@router.post(
    "/{entrega_id}/asignar",
    response_model=RespuestaExitosaDTO,
    summary="Asignar dron y crear vuelo para la entrega"
)
async def asignar_entrega(
    entrega_id: str,
    repo: EntregaRepository = Depends(get_entrega_repo),
    dron_repo: DronRepository = Depends(get_dron_repo),
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    servicio_flota: ServicioGestionFlota = Depends(get_servicio_flota),
    servicio_planificacion: ServicioPlanificacionRutas = Depends(get_servicio_planificacion),
    redis: RedisClient = Depends(get_redis_client),
):
    """
    Asigna el mejor dron disponible a una entrega y crea el plan de vuelo.
    """
    entrega = await repo.obtener_por_id(UUID(entrega_id))
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )
    
    if entrega.estado != EstadoEntrega.PENDIENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La entrega no está pendiente. Estado actual: {entrega.estado.value}"
        )
    
    # Obtener zonas restringidas activas
    from ...infrastructure.persistence.mongodb_repo import MongoDBConnection
    conn = MongoDBConnection()
    zona_repo = type('ZonaRepo', (), {
        'collection': conn.db.zonas_restringidas,
        '_from_document': lambda self, doc: __import__('backend.app.domain.entities.zona_restringida', fromlist=['ZonaRestringida']).ZonaRestringida(
            id=UUID(doc["id"]),
            codigo=doc.get("codigo", ""),
            nombre=doc.get("nombre", ""),
            coordenadas=[(c[0], c[1]) for c in doc.get("coordenadas", [])],
            altitud_min=doc.get("altitud_min", 0),
            altitud_max=doc.get("altitud_max", 500),
            tipo=__import__('backend.app.domain.enums.estados', fromlist=['TipoZona']).TipoZona(doc.get("tipo", "permanente")),
        )
    })()
    
    cursor = conn.db.zonas_restringidas.find({"activa": True})
    zonas = [zona_repo._from_document(doc) async for doc in cursor]
    servicio_planificacion.zonas_restringidas = zonas
    
    # Buscar mejor dron
    distancia_estimada = 0  # Se calcularía con geocoding
    mejor_dron = servicio_flota.obtener_mejor_dron_para_entrega(entrega, distancia_estimada)
    
    if not mejor_dron:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay drones disponibles para esta entrega"
        )
    
    # Crear vuelo
    from ...domain.entities.vuelo import Vuelo
    from ...domain.aggregates.vuelo_agg import AgregadoVuelo
    
    vuelo = Vuelo()
    vuelo.asignar_dron(mejor_dron.id)
    vuelo.asignar_entrega(entrega.id)
    
    # Calcular ruta
    origen = (
        entrega.direccion_origen.latitud,
        entrega.direccion_origen.longitud,
        entrega.direccion_origen.altitud or 50,
    )
    destino = (
        entrega.direccion_destino.latitud,
        entrega.direccion_destino.longitud,
        entrega.direccion_destino.altitud or 50,
    )
    
    try:
        plan = servicio_planificacion.calcular_ruta_optima(
            origen=origen,
            destino=destino,
            dron=mejor_dron,
            zonas_restringidas=zonas,
        )
        vuelo.establecer_plan(plan)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pudo calcular ruta: {str(e)}"
        )
    
    # Guardar todo
    await vuelo_repo.guardar(vuelo)
    
    entrega.asignar_dron(mejor_dron.id, vuelo.id)
    await repo.guardar(entrega)
    
    mejor_dron.estado = __import__('backend.app.domain.enums.estados', fromlist=['EstadoDron']).EstadoDron.ASIGNADO if hasattr(__import__('backend.app.domain.enums.estados', fromlist=['EstadoDron']).EstadoDron, 'ASIGNADO') else __import__('backend.app.domain.enums.estados', fromlist=['EstadoDron']).EstadoDron.CARGANDO
    await dron_repo.guardar(mejor_dron)
    
    # Actualizar Redis
    await redis.guardar_ruta_activa(
        vuelo.id,
        [wp.to_dict() for wp in plan.waypoints],
        prioridad=entrega.tipo.prioridad,
    )
    
    return RespuestaExitosaDTO(
        mensaje="Entrega asignada exitosamente",
        data={
            "entrega": entrega.to_dict(),
            "dron_asignado": mejor_dron.to_dict(),
            "vuelo": vuelo.to_dict(),
        }
    )


@router.post(
    "/{entrega_id}/completar",
    response_model=RespuestaExitosaDTO,
    summary="Marcar entrega como completada"
)
async def completar_entrega(
    entrega_id: str,
    repo: EntregaRepository = Depends(get_entrega_repo),
    vuelo_repo: VueloRepository = Depends(get_vuelo_repo),
    redis: RedisClient = Depends(get_redis_client),
):
    """Marca una entrega como entregada y finaliza el vuelo."""
    entrega = await repo.obtener_por_id(UUID(entrega_id))
    if not entrega:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrega no encontrada"
        )
    
    if entrega.estado != EstadoEntrega.EN_RUTA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden completar entregas EN_RUTA. Estado: {entrega.estado.value}"
        )
    
    entrega.marcar_entregado()
    await repo.guardar(entrega)
    
    # Finalizar vuelo asociado
    if entrega.vuelo_asignado_id:
        vuelo = await vuelo_repo.obtener_por_id(entrega.vuelo_asignado_id)
        if vuelo:
            vuelo.completar()
            await vuelo_repo.guardar(vuelo)
            await redis.eliminar_ruta(vuelo.id)
    
    return RespuestaExitosaDTO(
        mensaje="Entrega completada exitosamente",
        data=entrega.to_dict()
    )