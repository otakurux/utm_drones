"""entrega""" 
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from ..enums.estados import EstadoEntrega, TipoEntrega
from ..events.dominio_event import DominioEvent
from ..value_objects.direccion import DireccionDestino


@dataclass
class Paquete:
    """
    Entidad interna del agregado Pedido.
    Representa la carga física a transportar.
    """
    id: UUID = field(default_factory=uuid4)
    peso_kg: float = 0.0
    dimensiones_cm: str = ""         # "30x20x15"
    fragil: bool = False
    requiere_refrigeracion: bool = False
    descripcion: str = ""

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "peso_kg": self.peso_kg,
            "dimensiones_cm": self.dimensiones_cm,
            "fragil": self.fragil,
            "requiere_refrigeracion": self.requiere_refrigeracion,
            "descripcion": self.descripcion,
        }


@dataclass
class Entrega:
    """
    Entidad: Entrega (también conocida como Pedido en el agregado)
    Identificada por número de pedido único con ciclo de vida completo.
    """
    # Identidad
    id: UUID = field(default_factory=uuid4)
    numero_pedido: str = ""          # Identificador de negocio (ej: "PED-2024-000123")
    cliente_id: Optional[UUID] = None
    
    # Atributos de negocio
    tipo: TipoEntrega = TipoEntrega.GENERAL
    prioridad: int = field(init=False)  # Calculado automáticamente del tipo
    
    # Carga
    paquete: Paquete = field(default_factory=Paquete)
    
    # Ubicaciones
    direccion_origen: DireccionDestino = field(default_factory=lambda: DireccionDestino(0, 0))
    direccion_destino: DireccionDestino = field(default_factory=lambda: DireccionDestino(0, 0))
    
    # Estado
    estado: EstadoEntrega = EstadoEntrega.PENDIENTE
    dron_asignado_id: Optional[UUID] = None
    vuelo_asignado_id: Optional[UUID] = None
    
    # Timestamps
    fecha_creacion: datetime = field(default_factory=datetime.utcnow)
    fecha_asignacion: Optional[datetime] = None
    fecha_inicio_ruta: Optional[datetime] = None
    fecha_entrega: Optional[datetime] = None
    
    # Métricas
    tiempo_espera_minutos: float = 0.0
    
    # Eventos
    _eventos: List[DominioEvent] = field(default_factory=list, repr=False)

    def __post_init__(self):
        """Calcula la prioridad base según el tipo de entrega."""
        self.prioridad = self.tipo.prioridad

    # ============================================================
    # COMPORTAMIENTO DEL DOMINIO
    # ============================================================

    def calcular_score_prioridad(self) -> float:
        """
        Calcula el score final de prioridad considerando tiempo de espera.
        Aumenta la prioridad cada 5 minutos de espera.
        """
        if self.estado != EstadoEntrega.PENDIENTE:
            return float(self.prioridad)
        
        minutos_espera = (datetime.utcnow() - self.fecha_creacion).total_seconds() / 60
        factor_tiempo = minutos_espera / 5  # +1 punto cada 5 minutos
        return float(self.prioridad) + factor_tiempo

    def asignar_dron(self, dron_id: UUID, vuelo_id: UUID) -> None:
        """Asigna un dron y vuelo a esta entrega."""
        if self.estado != EstadoEntrega.PENDIENTE:
            raise ValueError(f"No se puede asignar dron. Estado: {self.estado}")
        
        self.dron_asignado_id = dron_id
        self.vuelo_asignado_id = vuelo_id
        self.estado = EstadoEntrega.ASIGNADA
        self.fecha_asignacion = datetime.utcnow()

    def iniciar_entrega(self) -> None:
        """Marca el inicio de la ruta de entrega."""
        if self.estado != EstadoEntrega.ASIGNADA:
            raise ValueError(f"No se puede iniciar entrega. Estado: {self.estado}")
        
        self.estado = EstadoEntrega.EN_RUTA
        self.fecha_inicio_ruta = datetime.utcnow()

    def marcar_entregado(self) -> None:
        """Confirma la entrega exitosa."""
        if self.estado != EstadoEntrega.EN_RUTA:
            raise ValueError(f"No se puede completar entrega. Estado: {self.estado}")
        
        self.estado = EstadoEntrega.ENTREGADO
        self.fecha_entrega = datetime.utcnow()

    def marcar_fallido(self, motivo: str = "") -> None:
        """Marca la entrega como fallida."""
        self.estado = EstadoEntrega.FALLIDO
        self.fecha_entrega = datetime.utcnow()

    def es_critica(self) -> bool:
        """Determina si la entrega es de prioridad crítica."""
        return self.tipo == TipoEntrega.MEDICINA

    def obtener_eventos_pendientes(self) -> List[DominioEvent]:
        eventos = self._eventos.copy()
        self._eventos.clear()
        return eventos

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "numero_pedido": self.numero_pedido,
            "cliente_id": str(self.cliente_id) if self.cliente_id else None,
            "tipo": self.tipo.value,
            "prioridad": self.prioridad,
            "score_actual": round(self.calcular_score_prioridad(), 2),
            "paquete": self.paquete.to_dict(),
            "origen": self.direccion_origen.to_dict(),
            "destino": self.direccion_destino.to_dict(),
            "estado": self.estado.value,
            "dron_asignado_id": str(self.dron_asignado_id) if self.dron_asignado_id else None,
            "vuelo_asignado_id": str(self.vuelo_asignado_id) if self.vuelo_asignado_id else None,
            "fecha_creacion": self.fecha_creacion.isoformat(),
            "fecha_asignacion": self.fecha_asignacion.isoformat() if self.fecha_asignacion else None,
            "fecha_entrega": self.fecha_entrega.isoformat() if self.fecha_entrega else None,
            "es_critica": self.es_critica(),
        }