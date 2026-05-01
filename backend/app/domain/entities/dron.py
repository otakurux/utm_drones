"""dron""" 
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from ..enums.estados import EstadoDron
from ..events.dominio_event import DominioEvent
from ..events.dron_despego import DronDespego
from ..events.dron_mantenimiento import DronMantenimiento
from ..events.posicion_actualizada import PosicionActualizada


@dataclass
class Dron:
    """
    Entidad: Dron
    Identidad única que persiste en el tiempo independientemente de sus atributos.
    El número de serie es el identificador de negocio; el UUID es el identificador técnico.
    """
    # Identidad
    id: UUID = field(default_factory=uuid4)
    numero_serie: str = ""           # Identificador de negocio único (ej: "DRN-2024-001")
    
    # Atributos
    modelo: str = ""                 # "DJI Matrice 300", "Autel EVO II", etc.
    capacidad_carga_kg: float = 0.0
    bateria_maxima_mah: int = 0
    
    # Estado mutable
    bateria_porcentaje: float = 100.0
    estado: EstadoDron = EstadoDron.DISPONIBLE
    latitud: float = 0.0
    longitud: float = 0.0
    altitud: float = 0.0
    
    # Metadatos
    fecha_registro: datetime = field(default_factory=datetime.utcnow)
    ultima_actualizacion: datetime = field(default_factory=datetime.utcnow)
    total_vuelos: int = 0
    horas_vuelo_acumuladas: float = 0.0
    
    # Eventos de dominio pendientes (patón Unit of Work)
    _eventos: List[DominioEvent] = field(default_factory=list, repr=False)

    # ============================================================
    # COMPORTAMIENTO DEL DOMINIO (métodos que encapsulan reglas)
    # ============================================================

    def actualizar_posicion(
        self,
        lat: float,
        lng: float,
        alt: float,
        velocidad: float = 0.0,
        bateria: Optional[float] = None,
    ) -> PosicionActualizada:
        """
        Actualiza la posición GPS del dron y genera evento de dominio.
        Se invoca cada 500ms durante el vuelo.
        """
        self.latitud = lat
        self.longitud = lng
        self.altitud = alt
        self.ultima_actualizacion = datetime.utcnow()
        
        if bateria is not None:
            self.bateria_porcentaje = max(0.0, min(100.0, bateria))
        
        evento = PosicionActualizada(
            aggregate_id=self.id,
            dron_id=self.id,
            latitud=lat,
            longitud=lng,
            altitud=alt,
            velocidad=velocidad,
            bateria=self.bateria_porcentaje,
        )
        self._eventos.append(evento)
        return evento

    def despegar(self, vuelo_id: UUID) -> DronDespego:
        """
        Transiciona el dron a estado EN_VUELO y genera evento.
        Precondición: el dron debe estar DISPONIBLE y con batería > 20%.
        """
        if self.estado != EstadoDron.DISPONIBLE:
            raise ValueError(f"Dron {self.numero_serie} no está disponible. Estado actual: {self.estado}")
        
        if self.bateria_porcentaje < 20.0:
            raise ValueError(f"Batería insuficiente: {self.bateria_porcentaje}%. Mínimo requerido: 20%")
        
        self.estado = EstadoDron.EN_VUELO
        self.total_vuelos += 1
        self.ultima_actualizacion = datetime.utcnow()
        
        evento = DronDespego(
            aggregate_id=self.id,
            dron_id=self.id,
            vuelo_id=vuelo_id,
        )
        self._eventos.append(evento)
        return evento

    def aterrizar(self) -> None:
        """Finaliza el vuelo y retorna el dron a estado disponible (o carga)."""
        if self.estado != EstadoDron.EN_VUELO:
            raise ValueError(f"Dron {self.numero_serie} no está en vuelo")
        
        self.estado = EstadoDron.CARGANDO if self.bateria_porcentaje < 50 else EstadoDron.DISPONIBLE
        self.altitud = 0.0
        self.ultima_actualizacion = datetime.utcnow()

    def entrar_mantenimiento(self, motivo: str, detalles: str = "") -> DronMantenimiento:
        """
        Retira el dron de la flota operativa por mantenimiento o falla.
        """
        evento = DronMantenimiento(
            aggregate_id=self.id,
            dron_id=self.id,
            motivo=motivo,
            nivel_bateria=self.bateria_porcentaje,
            detalles_falla=detalles,
        )
        self.estado = EstadoDron.MANTENIMIENTO
        self._eventos.append(evento)
        return evento

    def recargar_bateria(self) -> None:
        """Simula recarga completa de batería."""
        self.bateria_porcentaje = 100.0
        if self.estado == EstadoDron.CARGANDO:
            self.estado = EstadoDron.DISPONIBLE
        self.ultima_actualizacion = datetime.utcnow()

    def esta_disponible(self) -> bool:
        """Verifica si el dron puede ser asignado a una nueva entrega."""
        return (
            self.estado == EstadoDron.DISPONIBLE
            and self.bateria_porcentaje >= 20.0
        )

    def agregar_horas_vuelo(self, horas: float) -> None:
        """Actualiza las horas acumuladas de vuelo."""
        self.horas_vuelo_acumuladas += horas
        self.ultima_actualizacion = datetime.utcnow()

    # ============================================================
    # MÉTODOS DE EVENTOS
    # ============================================================

    def obtener_eventos_pendientes(self) -> List[DominioEvent]:
        """Retorna y limpia los eventos pendientes (patrón Unit of Work)."""
        eventos = self._eventos.copy()
        self._eventos.clear()
        return eventos

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "numero_serie": self.numero_serie,
            "modelo": self.modelo,
            "capacidad_carga_kg": self.capacidad_carga_kg,
            "bateria_maxima_mah": self.bateria_maxima_mah,
            "bateria_porcentaje": round(self.bateria_porcentaje, 1),
            "estado": self.estado.value,
            "posicion": {
                "lat": self.latitud,
                "lng": self.longitud,
                "alt": self.altitud,
            },
            "fecha_registro": self.fecha_registro.isoformat(),
            "ultima_actualizacion": self.ultima_actualizacion.isoformat(),
            "total_vuelos": self.total_vuelos,
            "horas_vuelo_acumuladas": round(self.horas_vuelo_acumuladas, 2),
            "disponible": self.esta_disponible(),
        }