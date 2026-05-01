"""dron_mantenimiento"""
from dataclasses import dataclass
from uuid import UUID

from .dominio_event import DominioEvent


@dataclass(frozen=True)
class DronMantenimiento(DominioEvent):
    """
    Evento emitido cuando un dron entra en mantenimiento.
    Retira al dron de la flota disponible.
    """
    dron_id: UUID = None
    motivo: str = ""                    # bateria_critica | falla_hardware | mantenimiento_programado
    nivel_bateria: float = 0.0
    detalles_falla: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dron_id": str(self.dron_id),
            "motivo": self.motivo,
            "nivel_bateria": self.nivel_bateria,
            "detalles_falla": self.detalles_falla,
        })
        return base