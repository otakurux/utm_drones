"""vuelo""" 
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from ..enums.estados import EstadoVuelo
from ..events.dominio_event import DominioEvent
from ..events.conflicto_detectado import ConflictoDetectado
from ..events.entrega_completada import EntregaCompletada
from ..value_objects.plan_vuelo import PlanDeVuelo


@dataclass
class Vuelo:
    """
    Entidad: Vuelo
    Representa una instancia de vuelo asignada a un dron para cumplir una entrega.
    Es la raíz del agregado Vuelo.
    """
    # Identidad
    id: UUID = field(default_factory=uuid4)
    
    # Referencias (IDs externos, no navegación directa - DDD)
    dron_id: Optional[UUID] = None
    entrega_id: Optional[UUID] = None
    
    # Estado mutable
    estado: EstadoVuelo = EstadoVuelo.PLANIFICADO
    plan_vuelo: PlanDeVuelo = field(default_factory=PlanDeVuelo)
    
    # Timestamps
    fecha_creacion: datetime = field(default_factory=datetime.utcnow)
    fecha_despegue: Optional[datetime] = None
    fecha_completado: Optional[datetime] = None
    
    # Métricas de ejecución
    waypoint_actual: int = 0
    distancia_recorrida: float = 0.0
    
    # Eventos
    _eventos: List[DominioEvent] = field(default_factory=list, repr=False)

    # ============================================================
    # COMPORTAMIENTO DEL DOMINIO
    # ============================================================

    def asignar_dron(self, dron_id: UUID) -> None:
        """Asigna un dron a este vuelo."""
        if self.dron_id is not None:
            raise ValueError(f"Vuelo {self.id} ya tiene un dron asignado")
        self.dron_id = dron_id

    def asignar_entrega(self, entrega_id: UUID) -> None:
        """Vincula el vuelo con una entrega específica."""
        if self.entrega_id is not None:
            raise ValueError(f"Vuelo {self.id} ya tiene una entrega asignada")
        self.entrega_id = entrega_id

    def establecer_plan(self, plan: PlanDeVuelo) -> None:
        """Asigna el plan de vuelo calculado por el servicio de planificación."""
        self.plan_vuelo = plan

    def iniciar(self) -> None:
        """
        Marca el inicio del vuelo.
        Precondición: debe tener dron asignado y plan de vuelo válido.
        """
        if self.dron_id is None:
            raise ValueError("No se puede iniciar vuelo sin dron asignado")
        if not self.plan_vuelo.waypoints:
            raise ValueError("No se puede iniciar vuelo sin plan de vuelo")
        
        self.estado = EstadoVuelo.EN_RUTA
        self.fecha_despegue = datetime.utcnow()
        self.waypoint_actual = 0

    def avanzar_waypoint(self) -> bool:
        """
        Avanza al siguiente waypoint.
        Retorna True si quedan más waypoints, False si llegó al destino.
        """
        self.waypoint_actual += 1
        if self.waypoint_actual >= len(self.plan_vuelo.waypoints):
            return False
        return True

    def reportar_conflicto(
        self,
        otro_vuelo_id: UUID,
        otro_dron_id: UUID,
        lat: float,
        lng: float,
        alt: float,
        distancia: float,
        tiempo: float,
    ) -> ConflictoDetectado:
        """
        Genera evento de conflicto cuando se detecta intersección de rutas.
        """
        evento = ConflictoDetectado(
            aggregate_id=self.id,
            vuelo_a_id=self.id,
            vuelo_b_id=otro_vuelo_id,
            dron_a_id=self.dron_id,
            dron_b_id=otro_dron_id,
            punto_interseccion_lat=lat,
            punto_interseccion_lng=lng,
            punto_interseccion_alt=alt,
            distancia_estimada=distancia,
            tiempo_para_conflicto=tiempo,
            severidad="alta" if distancia < 10 else "media",
        )
        self._eventos.append(evento)
        return evento

    def completar(self) -> EntregaCompletada:
        """
        Finaliza el vuelo exitosamente.
        Genera evento EntregaCompletada para persistencia en MongoDB.
        """
        if self.estado != EstadoVuelo.EN_RUTA:
            raise ValueError(f"No se puede completar vuelo en estado {self.estado}")
        
        self.estado = EstadoVuelo.COMPLETADO
        self.fecha_completado = datetime.utcnow()
        
        # Última posición del plan como punto de entrega
        ultimo_wp = self.plan_vuelo.waypoints[-1] if self.plan_vuelo.waypoints else None
        
        evento = EntregaCompletada(
            aggregate_id=self.id,
            entrega_id=self.entrega_id,
            dron_id=self.dron_id,
            vuelo_id=self.id,
            latitud_entrega=ultimo_wp.latitud if ultimo_wp else 0.0,
            longitud_entrega=ultimo_wp.longitud if ultimo_wp else 0.0,
        )
        self._eventos.append(evento)
        return evento

    def cancelar(self, motivo: str = "") -> None:
        """Cancela el vuelo por emergencia u otra causa."""
        self.estado = EstadoVuelo.CANCELADO
        self.fecha_completado = datetime.utcnow()

    def emergencia(self, motivo: str = "") -> None:
        """Activa modo emergencia (aterrizaje forzado)."""
        self.estado = EstadoVuelo.EMERGENCIA

    def obtener_eventos_pendientes(self) -> List[DominioEvent]:
        eventos = self._eventos.copy()
        self._eventos.clear()
        return eventos

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "dron_id": str(self.dron_id) if self.dron_id else None,
            "entrega_id": str(self.entrega_id) if self.entrega_id else None,
            "estado": self.estado.value,
            "plan_vuelo": self.plan_vuelo.to_dict(),
            "fecha_creacion": self.fecha_creacion.isoformat(),
            "fecha_despegue": self.fecha_despegue.isoformat() if self.fecha_despegue else None,
            "fecha_completado": self.fecha_completado.isoformat() if self.fecha_completado else None,
            "waypoint_actual": self.waypoint_actual,
            "distancia_recorrida": round(self.distancia_recorrida, 2),
            "progreso": f"{self.waypoint_actual}/{len(self.plan_vuelo.waypoints)}",
        }