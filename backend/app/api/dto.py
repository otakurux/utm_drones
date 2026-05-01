from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# DTOs para Dron
# ============================================================

class DronCreateDTO(BaseModel):
    numero_serie: str = Field(..., min_length=3, max_length=50, example="DRN-2024-001")
    modelo: str = Field(..., min_length=1, max_length=100, example="DJI Matrice 300")
    capacidad_carga_kg: float = Field(..., ge=0, le=50, example=2.5)
    bateria_maxima_mah: int = Field(..., ge=1000, le=50000, example=6000)
    latitud: float = Field(0.0, ge=-90, le=90, example=-16.5000)
    longitud: float = Field(0.0, ge=-180, le=180, example=-68.1500)
    altitud: float = Field(0.0, ge=0, le=500, example=0.0)


class DronUpdateDTO(BaseModel):
    modelo: Optional[str] = None
    capacidad_carga_kg: Optional[float] = Field(None, ge=0, le=50)
    bateria_maxima_mah: Optional[int] = Field(None, ge=1000, le=50000)


class DronResponseDTO(BaseModel):
    id: str
    numero_serie: str
    modelo: str
    capacidad_carga_kg: float
    bateria_maxima_mah: int
    bateria_porcentaje: float
    estado: str
    posicion: dict
    fecha_registro: datetime
    ultima_actualizacion: datetime
    total_vuelos: int
    horas_vuelo_acumuladas: float
    disponible: bool

    class Config:
        from_attributes = True


# ============================================================
# DTOs para Entrega
# ============================================================

class PaqueteDTO(BaseModel):
    peso_kg: float = Field(..., ge=0, le=50, example=1.5)
    dimensiones_cm: str = Field(default="", example="30x20x15")
    fragil: bool = Field(default=False)
    requiere_refrigeracion: bool = Field(default=False)
    descripcion: str = Field(default="")


class DireccionDTO(BaseModel):
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    altitud: float = Field(default=0.0, ge=0, le=500)
    instrucciones: str = Field(default="")


class EntregaCreateDTO(BaseModel):
    numero_pedido: str = Field(..., min_length=1, example="PED-2024-000123")
    cliente_id: Optional[str] = None
    tipo: str = Field(..., pattern="^(medicina|alimentos|farmacia|general)$")
    paquete: PaqueteDTO
    direccion_origen: DireccionDTO
    direccion_destino: DireccionDTO


class EntregaResponseDTO(BaseModel):
    id: str
    numero_pedido: str
    cliente_id: Optional[str]
    tipo: str
    prioridad: int
    score_actual: float
    paquete: dict
    origen: dict
    destino: dict
    estado: str
    dron_asignado_id: Optional[str]
    vuelo_asignado_id: Optional[str]
    fecha_creacion: datetime
    fecha_asignacion: Optional[datetime]
    fecha_entrega: Optional[datetime]
    es_critica: bool

    class Config:
        from_attributes = True


# ============================================================
# DTOs para Vuelo
# ============================================================

class WaypointDTO(BaseModel):
    latitud: float
    longitud: float
    altitud: float = Field(default=50.0, ge=30, le=120)


class VueloCreateDTO(BaseModel):
    dron_id: str
    entrega_id: str
    waypoints: List[WaypointDTO] = Field(..., min_length=2)


class VueloResponseDTO(BaseModel):
    id: str
    dron_id: Optional[str]
    entrega_id: Optional[str]
    estado: str
    plan_vuelo: dict
    fecha_creacion: datetime
    fecha_despegue: Optional[datetime]
    fecha_completado: Optional[datetime]
    waypoint_actual: int
    distancia_recorrida: float
    progreso: str

    class Config:
        from_attributes = True


# ============================================================
# DTOs para Zona Restringida
# ============================================================

class ZonaCreateDTO(BaseModel):
    codigo: str = Field(..., min_length=1, example="ZRP-LPZ-001")
    nombre: str = Field(..., min_length=1, example="Aeropuerto El Alto")
    descripcion: str = Field(default="")
    coordenadas: List[List[float]] = Field(
        ...,
        example=[[-16.5000, -68.1500], [-16.5100, -68.1500], [-16.5100, -68.1600], [-16.5000, -68.1600], [-16.5000, -68.1500]],
        description="Lista de [lat, lng] que forman el polígono cerrado"
    )
    altitud_min: float = Field(default=0.0, ge=0)
    altitud_max: float = Field(default=500.0, ge=0)
    tipo: str = Field(default="permanente", pattern="^(permanente|temporal)$")
    vigencia_desde: Optional[datetime] = None
    vigencia_hasta: Optional[datetime] = None
    autoridad_emisora: str = Field(default="ANAC")


class ZonaResponseDTO(BaseModel):
    id: str
    codigo: str
    nombre: str
    descripcion: str
    coordenadas: List[List[float]]
    altitud_min: float
    altitud_max: float
    tipo: str
    vigencia_desde: Optional[datetime]
    vigencia_hasta: Optional[datetime]
    autoridad_emisora: str
    activa: bool
    vigente: bool

    class Config:
        from_attributes = True


# ============================================================
# DTOs para Dashboard/Estadísticas
# ============================================================

class EstadoFlotaDTO(BaseModel):
    total_drones: int
    disponibles: int
    en_vuelo: int
    cargando: int
    mantenimiento: int
    bateria_promedio: float
    entregas_activas: int


class AlertaDTO(BaseModel):
    tipo: str
    dron_id: Optional[str]
    numero_serie: Optional[str]
    mensaje: str
    severidad: str


class EstadisticasDTO(BaseModel):
    estado_flota: EstadoFlotaDTO
    alertas: List[AlertaDTO]
    entregas_pendientes: int
    entregas_criticas: bool
    vuelos_activos: int


class PosicionDronDTO(BaseModel):
    dron_id: str
    lat: float
    lng: float
    alt: float
    velocidad: float
    bateria: float
    timestamp: Optional[str]


# ============================================================
# DTOs para Respuestas Genéricas
# ============================================================

class RespuestaExitosaDTO(BaseModel):
    exito: bool = True
    mensaje: str
    data: Optional[dict] = None


class RespuestaErrorDTO(BaseModel):
    exito: bool = False
    error: str
    detalle: Optional[str] = None


class ListaPaginadaDTO(BaseModel):
    items: List[dict]
    total: int
    skip: int
    limit: int