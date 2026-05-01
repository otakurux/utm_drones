"""dron_despego""" 
from dataclasses import dataclass
from uuid import UUID

from .dominio_event import DominioEvent


@dataclass(frozen=True)
class DronDespego(DominioEvent):
    """
    Evento emitido cuando un dron inicia su misión de vuelo.
    Publicado vía Redis Pub/Sub para actualizar el dashboard en tiempo real.
    """
    dron_id: UUID = None
    vuelo_id: UUID = None

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dron_id": str(self.dron_id),
            "vuelo_id": str(self.vuelo_id),
        })
        return base