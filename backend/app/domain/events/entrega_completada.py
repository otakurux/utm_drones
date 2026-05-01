"""entrega_completada""" 
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .dominio_event import DominioEvent


@dataclass(frozen=True)
class EntregaCompletada(DominioEvent):
    """
    Evento emitido al finalizar exitosamente una entrega.
    Persiste el estado ENTREGADO en MongoDB.
    """
    entrega_id: UUID = None
    dron_id: UUID = None
    vuelo_id: UUID = None
    latitud_entrega: float = 0.0
    longitud_entrega: float = 0.0
    timestamp_entrega: datetime = None

    def __post_init__(self):
        if self.timestamp_entrega is None:
            object.__setattr__(self, 'timestamp_entrega', datetime.utcnow())

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "entrega_id": str(self.entrega_id),
            "dron_id": str(self.dron_id),
            "vuelo_id": str(self.vuelo_id),
            "coordenadas_entrega": {
                "lat": self.latitud_entrega,
                "lng": self.longitud_entrega,
            },
            "timestamp_entrega": self.timestamp_entrega.isoformat() if self.timestamp_entrega else None,
        })
        return base