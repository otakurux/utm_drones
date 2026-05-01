"""geocerca""" 
from dataclasses import dataclass, field
from typing import List, Tuple
from uuid import UUID, uuid4


@dataclass
class Geocerca:
    """
    Value Object que define una zona de seguridad alrededor de una ruta o dron.
    Puede ser circular (radio) o poligonal (lista de coordenadas).
    """
    id: UUID = field(default_factory=uuid4)
    tipo: str = "circular"           # circular | poligonal
    radio_metros: float = 15.0       # Para tipo circular (separación mínima de seguridad)
    poligono: List[Tuple[float, float]] = field(default_factory=list)  # [(lat, lng), ...]
    altitud_min: float = 0.0
    altitud_max: float = 150.0

    def contiene_punto(self, lat: float, lng: float, alt: float = 0) -> bool:
        """
        Verifica si un punto está dentro de la geocerca.
        Para geocercas circulares usa distancia euclidiana simplificada.
        """
        if self.tipo == "circular" and self.poligono:
            centro_lat, centro_lng = self.poligono[0]
            import math
            distancia = math.sqrt((lat - centro_lat)**2 + (lng - centro_lng)**2) * 111320
            return distancia <= self.radio_metros and self.altitud_min <= alt <= self.altitud_max
        
        # Para poligonales se necesitaría algoritmo point-in-polygon (ray casting)
        return False

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "tipo": self.tipo,
            "radio_metros": self.radio_metros,
            "poligono": self.poligono,
            "altitud_min": self.altitud_min,
            "altitud_max": self.altitud_max,
        }