"""dominio_event"""
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DominioEvent(ABC):
    """
    Clase base para todos los eventos de dominio.
    Los eventos son inmutables y representan hechos ocurridos en el pasado.
    """
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    aggregate_id: Optional[UUID] = None

    def to_dict(self) -> dict:
        return {
            "event_id": str(self.event_id),
            "timestamp": self.timestamp.isoformat(),
            "tipo": self.__class__.__name__,
            "aggregate_id": str(self.aggregate_id) if self.aggregate_id else None,
        }