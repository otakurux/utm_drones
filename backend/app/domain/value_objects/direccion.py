"""direccion""" 
from dataclasses import dataclass


@dataclass(frozen=True)
class DireccionDestino:
    """
    Value Object que representa la ubicación de entrega.
    Inmutable - la dirección no cambia una vez creada la entrega.
    """
    latitud: float
    longitud: float
    altitud: float = 0.0            # Altitud del punto de entrega (terrazas, balcones)
    instrucciones: str = ""          # "Dejar en recepción", "Timbra al 3er piso", etc.

    def to_dict(self) -> dict:
        return {
            "latitud": self.latitud,
            "longitud": self.longitud,
            "altitud": self.altitud,
            "instrucciones": self.instrucciones,
        }