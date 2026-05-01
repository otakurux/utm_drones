"""zonas""" 
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..dto import (
    ZonaCreateDTO,
    ZonaResponseDTO,
    RespuestaExitosaDTO,
)
from ..dependencies import (
    get_zona_repo,
    verificar_mongodb_conectado,
)
from ...domain.entities.zona_restringida import ZonaRestringida
from ...domain.enums.estados import TipoZona
from ...infrastructure.persistence.mongodb_repo import ZonaRepository


router = APIRouter(
    prefix="/zonas",
    tags=["Zonas Restringidas"],
    dependencies=[Depends(verificar_mongodb_conectado)],
)


@router.post(
    "",
    response_model=RespuestaExitosaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nueva zona restringida"
)
async def crear_zona(
    dto: ZonaCreateDTO,
    repo: ZonaRepository = Depends(get_zona_repo),
):
    """Crea una nueva zona restringida para vuelos."""
    # Verificar código único
    existente = await repo.obtener_por_codigo(dto.codigo)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una zona con código {dto.codigo}"
        )
    
    # Validar polígono cerrado
    coordenadas = [(c[0], c[1]) for c in dto.coordenadas]
    if len(coordenadas) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El polígono debe tener al menos 3 coordenadas"
        )
    
    # Cerrar polígono si no está cerrado
    if coordenadas[0] != coordenadas[-1]:
        coordenadas.append(coordenadas[0])
    
    zona = ZonaRestringida(
        codigo=dto.codigo,
        nombre=dto.nombre,
        descripcion=dto.descripcion,
        coordenadas=coordenadas,
        altitud_min=dto.altitud_min,
        altitud_max=dto.altitud_max,
        tipo=TipoZona(dto.tipo),
        vigencia_desde=dto.vigencia_desde or __import__('datetime').datetime.utcnow(),
        vigencia_hasta=dto.vigencia_hasta,
        autoridad_emisora=dto.autoridad_emisora,
    )
    
    await repo.guardar(zona)
    
    return RespuestaExitosaDTO(
        mensaje="Zona restringida creada exitosamente",
        data=zona.to_dict()
    )


@router.get(
    "",
    response_model=List[ZonaResponseDTO],
    summary="Listar zonas restringidas"
)
async def listar_zonas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    solo_activas: bool = Query(False, description="Filtrar solo zonas vigentes"),
    repo: ZonaRepository = Depends(get_zona_repo),
):
    """Lista zonas restringidas con opción de filtrar solo activas."""
    if solo_activas:
        zonas = await repo.listar_activas()
    else:
        zonas = await repo.listar_todas(skip, limit)
    
    return [ZonaResponseDTO(**z.to_dict()) for z in zonas]


@router.get(
    "/activas",
    response_model=List[ZonaResponseDTO],
    summary="Listar zonas restringidas activas y vigentes"
)
async def listar_zonas_activas(
    repo: ZonaRepository = Depends(get_zona_repo),
):
    """Lista solo las zonas que están vigentes en este momento."""
    zonas = await repo.listar_activas()
    return [ZonaResponseDTO(**z.to_dict()) for z in zonas]


@router.get(
    "/{zona_id}",
    response_model=ZonaResponseDTO,
    summary="Obtener zona por ID"
)
async def obtener_zona(
    zona_id: str,
    repo: ZonaRepository = Depends(get_zona_repo),
):
    """Obtiene información detallada de una zona restringida."""
    zona = await repo.obtener_por_id(UUID(zona_id))
    if not zona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zona no encontrada"
        )
    return ZonaResponseDTO(**zona.to_dict())


@router.patch(
    "/{zona_id}/desactivar",
    response_model=RespuestaExitosaDTO,
    summary="Desactivar zona restringida"
)
async def desactivar_zona(
    zona_id: str,
    repo: ZonaRepository = Depends(get_zona_repo),
):
    """Desactiva una zona restringida (no elimina)."""
    zona = await repo.obtener_por_id(UUID(zona_id))
    if not zona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zona no encontrada"
        )
    
    await repo.desactivar(UUID(zona_id))
    
    return RespuestaExitosaDTO(
        mensaje="Zona desactivada exitosamente",
        data={"id": zona_id, "activa": False}
    )


@router.delete(
    "/{zona_id}",
    response_model=RespuestaExitosaDTO,
    summary="Eliminar zona restringida permanentemente"
)
async def eliminar_zona(
    zona_id: str,
    repo: ZonaRepository = Depends(get_zona_repo),
):
    """Elimina permanentemente una zona restringida."""
    zona = await repo.obtener_por_id(UUID(zona_id))
    if not zona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zona no encontrada"
        )
    
    from ...infrastructure.persistence.mongodb_repo import MongoDBConnection
    conn = MongoDBConnection()
    result = await conn.db.zonas_restringidas.delete_one({"_id": zona_id})
    
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo eliminar la zona"
        )
    
    return RespuestaExitosaDTO(mensaje="Zona eliminada permanentemente")