"""drones""" 
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..dto import (
    DronCreateDTO,
    DronUpdateDTO,
    DronResponseDTO,
    RespuestaExitosaDTO,
    RespuestaErrorDTO,
    PosicionDronDTO,
)
from ..dependencies import (
    get_dron_repo,
    get_redis_client,
    get_servicio_flota,
    verificar_mongodb_conectado,
)
from ...domain.entities.dron import Dron
from ...domain.enums.estados import EstadoDron
from ...infrastructure.persistence.mongodb_repo import DronRepository
from ...infrastructure.persistence.redis_client import RedisClient
from ...domain.services.servicio_gestion_flota import ServicioGestionFlota


router = APIRouter(
    prefix="/drones",
    tags=["Drones"],
    dependencies=[Depends(verificar_mongodb_conectado)],
)


@router.post(
    "",
    response_model=RespuestaExitosaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo dron en la flota"
)
async def crear_dron(
    dto: DronCreateDTO,
    repo: DronRepository = Depends(get_dron_repo),
    servicio_flota: ServicioGestionFlota = Depends(get_servicio_flota),
):
    """Registra un nuevo dron en el sistema."""
    # Verificar número de serie único
    existente = await repo.obtener_por_serie(dto.numero_serie)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un dron con número de serie {dto.numero_serie}"
        )
    
    dron = Dron(
        numero_serie=dto.numero_serie,
        modelo=dto.modelo,
        capacidad_carga_kg=dto.capacidad_carga_kg,
        bateria_maxima_mah=dto.bateria_maxima_mah,
        latitud=dto.latitud,
        longitud=dto.longitud,
        altitud=dto.altitud,
    )
    
    await repo.guardar(dron)
    servicio_flota.registrar_dron(dron)
    
    return RespuestaExitosaDTO(
        mensaje="Dron registrado exitosamente",
        data=dron.to_dict()
    )


@router.get(
    "",
    response_model=List[DronResponseDTO],
    summary="Listar todos los drones"
)
async def listar_drones(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    estado: Optional[str] = Query(None, pattern="^(disponible|en_vuelo|cargando|mantenimiento)$"),
    repo: DronRepository = Depends(get_dron_repo),
):
    """Lista drones con paginación y filtro opcional por estado."""
    if estado:
        drones = await repo.listar_por_estado(EstadoDron(estado))
    else:
        drones = await repo.listar_todos(skip, limit)
    
    return [DronResponseDTO(**d.to_dict()) for d in drones]


@router.get(
    "/disponibles",
    response_model=List[DronResponseDTO],
    summary="Listar drones disponibles para asignación"
)
async def listar_disponibles(
    repo: DronRepository = Depends(get_dron_repo),
):
    """Lista drones disponibles (estado disponible + batería >= 20%)."""
    drones = await repo.listar_disponibles()
    return [DronResponseDTO(**d.to_dict()) for d in drones]


@router.get(
    "/{dron_id}",
    response_model=DronResponseDTO,
    summary="Obtener dron por ID"
)
async def obtener_dron(
    dron_id: str,
    repo: DronRepository = Depends(get_dron_repo),
):
    """Obtiene la información detallada de un dron."""
    dron = await repo.obtener_por_id(UUID(dron_id))
    if not dron:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron no encontrado"
        )
    return DronResponseDTO(**dron.to_dict())


@router.get(
    "/{dron_id}/posicion",
    response_model=PosicionDronDTO,
    summary="Obtener posición en tiempo real del dron"
)
async def obtener_posicion_dron(
    dron_id: str,
    redis: RedisClient = Depends(get_redis_client),
):
    """
    Obtiene la última posición conocida del dron desde Redis.
    Actualización cada 500ms durante vuelo.
    """
    posicion = await redis.obtener_posicion(dron_id)
    if not posicion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Posición no disponible. El dron no está reportando."
        )
    return PosicionDronDTO(**posicion)


@router.patch(
    "/{dron_id}",
    response_model=RespuestaExitosaDTO,
    summary="Actualizar información del dron"
)
async def actualizar_dron(
    dron_id: str,
    dto: DronUpdateDTO,
    repo: DronRepository = Depends(get_dron_repo),
):
    """Actualiza información básica del dron."""
    dron = await repo.obtener_por_id(UUID(dron_id))
    if not dron:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron no encontrado"
        )
    
    if dto.modelo:
        dron.modelo = dto.modelo
    if dto.capacidad_carga_kg:
        dron.capacidad_carga_kg = dto.capacidad_carga_kg
    if dto.bateria_maxima_mah:
        dron.bateria_maxima_mah = dto.bateria_maxima_mah
    
    await repo.guardar(dron)
    
    return RespuestaExitosaDTO(
        mensaje="Dron actualizado exitosamente",
        data=dron.to_dict()
    )


@router.post(
    "/{dron_id}/recargar",
    response_model=RespuestaExitosaDTO,
    summary="Simular recarga de batería del dron"
)
async def recargar_dron(
    dron_id: str,
    repo: DronRepository = Depends(get_dron_repo),
):
    """Recarga la batería del dron al 100%."""
    dron = await repo.obtener_por_id(UUID(dron_id))
    if not dron:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron no encontrado"
        )
    
    dron.recargar_bateria()
    await repo.guardar(dron)
    
    return RespuestaExitosaDTO(
        mensaje="Batería recargada exitosamente",
        data={"bateria_porcentaje": dron.bateria_porcentaje, "estado": dron.estado.value}
    )


@router.post(
    "/{dron_id}/mantenimiento",
    response_model=RespuestaExitosaDTO,
    summary="Enviar dron a mantenimiento"
)
async def enviar_mantenimiento(
    dron_id: str,
    motivo: str = Query(..., description="Motivo del mantenimiento"),
    detalles: str = Query("", description="Detalles adicionales"),
    repo: DronRepository = Depends(get_dron_repo),
    servicio_flota: ServicioGestionFlota = Depends(get_servicio_flota),
):
    """Envía un dron a mantenimiento y genera evento correspondiente."""
    dron = await repo.obtener_por_id(UUID(dron_id))
    if not dron:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron no encontrado"
        )
    
    evento = dron.entrar_mantenimiento(motivo, detalles)
    await repo.guardar(dron)
    
    # Actualizar servicio de flota
    servicio_flota._drones[str(dron.id)] = dron
    
    return RespuestaExitosaDTO(
        mensaje="Dron enviado a mantenimiento",
        data={"evento": evento.to_dict(), "dron": dron.to_dict()}
    )


@router.delete(
    "/{dron_id}",
    response_model=RespuestaExitosaDTO,
    summary="Eliminar dron permanentemente"
)
async def eliminar_dron(
    dron_id: str,
    repo: DronRepository = Depends(get_dron_repo),
):
    """Elimina un dron del sistema permanentemente."""
    eliminado = await repo.eliminar(UUID(dron_id))
    if not eliminado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dron no encontrado"
        )
    
    return RespuestaExitosaDTO(mensaje="Dron eliminado exitosamente")