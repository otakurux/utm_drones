"""zona_restringida""" 
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple
from uuid import UUID, uuid4

from ..enums.estados import TipoZona


@dataclass
class ZonaRestringida:
    """
    Entidad: ZonaRestringida
    Área geográfica con restricciones de vuelo, identificada por coordenadas y vigencia.
    """
    # Identidad
    id: UUID = field(default_factory=uuid4)
    codigo: str = ""                 # Código regulatorio (ej: "ZRP-LPZ-001")
    nombre: str = ""                 # "Aeropuerto El Alto", "Zona Hospitalaria", etc.
    descripcion: str = ""
    
    # Geometría (polígono de coordenadas)
    coordenadas: List[Tuple[float, float]] = field(default_factory=list)
    # [(lat1, lng1), (lat2, lng2), ...] - Polígono cerrado
    
    # Restricciones de altitud
    altitud_min: float = 0.0
    altitud_max: float = 500.0       # 0-500m = prohibido total
    
    # Vigencia
    tipo: TipoZona = TipoZona.PERMANENTE
    vigencia_desde: datetime = field(default_factory=datetime.utcnow)
    vigencia_hasta: Optional[datetime] = None  # None si es permanente
    
    # Metadatos
    autoridad_emisora: str = ""      # "ANAC", "FAA", "EASA", etc.
    fecha_creacion: datetime = field(default_factory=datetime.utcnow)
    activa: bool = True

    # ============================================================
    # COMPORTAMIENTO DEL DOMINIO
    # ============================================================

    def esta_vigente(self) -> bool:
        """Verifica si la zona está activa y dentro del período de vigencia."""
        if not self.activa:
            return False
        
        ahora = datetime.utcnow()
        
        if ahora < self.vigencia_desde:
            return False
        
        if self.tipo == TipoZona.TEMPORAL and self.vigencia_hasta:
            return ahora <= self.vigencia_hasta
        
        return True

    def contiene_punto(self, lat: float, lng: float, alt: float = 0) -> bool:
        """
        Verifica si un punto 3D está dentro de la zona restringida.
        Usa algoritmo ray-casting para polígonos.
        """
        if not self.esta_vigente():
            return False
        
        # Verificar altitud primero
        if not (self.altitud_min <= alt <= self.altitud_max):
            return False
        
        # Algoritmo point-in-polygon (ray casting)
        n = len(self.coordenadas)
        if n < 3:
            return False
        
        inside = False
        j = n - 1
        
        for i in range(n):
            xi, yi = self.coordenadas[i]
            xj, yj = self.coordenadas[j]
            
            if ((yi > lng) != (yj > lng)) and (lat < (xj - xi) * (lng - yi) / (yj - yi) + xi):
                inside = not inside
            
            j = i
        
        return inside

    def intersecta_ruta(self, waypoints: List[Tuple[float, float, float]]) -> bool:
        """
        Verifica si una ruta (lista de waypoints) intersecta esta zona.
        waypoints: [(lat, lng, alt), ...]
        """
        for lat, lng, alt in waypoints:
            if self.contiene_punto(lat, lng, alt):
                return True
        return False

    def desactivar(self) -> None:
        """Desactiva la zona (para zonas temporales que expiran)."""
        self.activa = False

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "codigo": self.codigo,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "coordenadas": self.coordenadas,
            "altitud_min": self.altitud_min,
            "altitud_max": self.altitud_max,
            "tipo": self.tipo.value,
            "vigencia_desde": self.vigencia_desde.isoformat(),
            "vigencia_hasta": self.vigencia_hasta.isoformat() if self.vigencia_hasta else None,
            "autoridad_emisora": self.autoridad_emisora,
            "activa": self.activa,
            "vigente": self.esta_vigente(),
        }