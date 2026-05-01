"""conflicto_detectado""" 
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from .dominio_event import DominioEvent


@dataclass(frozen=True)
class ConflictoDetectado(DominioEvent):
    """
    Evento crítico emitido cuando dos rutas activas presentan riesgo de intersección.
    Requiere resolución inmediata por el ServicioDeteccionConflictos.
    """
    vuelo_a_id: UUID = None
    vuelo_b_id: UUID = None
    dron_a_id: UUID = None
    dron_b_id: UUID = None
    punto_interseccion_lat: float = 0.0
    punto_interseccion_lng: float = 0.0
    punto_interseccion_alt: float = 0.0
    distancia_estimada: float = 0.0     # metros
    tiempo_para_conflicto: float = 0.0   # segundos
    severidad: str = "alta"              # alta | media | baja

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "vuelo_a_id": str(self.vuelo_a_id),
            "vuelo_b_id": str(self.vuelo_b_id),
            "dron_a_id": str(self.dron_a_id),
            "dron_b_id": str(self.dron_b_id),
            "punto_interseccion": {
                "lat": self.punto_interseccion_lat,
                "lng": self.punto_interseccion_lng,
                "alt": self.punto_interseccion_alt,
            },
            "distancia_estimada": self.distancia_estimada,
            "tiempo_para_conflicto": self.tiempo_para_conflicto,
            "severidad": self.severidad,
        })
        return base