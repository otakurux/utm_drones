"""posicion_actualizada""" 
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .dominio_event import DominioEvent


@dataclass(frozen=True)
class PosicionActualizada(DominioEvent):
    """
    Evento emitido cada 500ms con la posición GPS actual del dron.
    Almacenado en Redis HSET y publicado vía Pub/Sub.
    """
    dron_id: UUID = None
    latitud: float = 0.0
    longitud: float = 0.0
    altitud: float = 0.0
    velocidad: float = 0.0          # m/s
    bateria: float = 100.0          # porcentaje
    timestamp_posicion: datetime = None

    def __post_init__(self):
        if self.timestamp_posicion is None:
            object.__setattr__(self, 'timestamp_posicion', datetime.utcnow())

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dron_id": str(self.dron_id),
            "latitud": self.latitud,
            "longitud": self.longitud,
            "altitud": self.altitud,
            "velocidad": self.velocidad,
            "bateria": self.bateria,
            "timestamp_posicion": self.timestamp_posicion.isoformat() if self.timestamp_posicion else None,
        })
        return base