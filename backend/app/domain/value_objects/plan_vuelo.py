"""plan_vuelo""" 
from dataclasses import dataclass, field
from typing import List
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Waypoint:
    """
    Punto de ruta en el espacio aéreo 3D.
    Inmutable - si cambia, se crea un nuevo PlanDeVuelo.
    """
    orden: int
    latitud: float
    longitud: float
    altitud: float          # metros sobre el nivel del mar
    velocidad_max: float = 15.0   # m/s (default 54 km/h para entregas urbanas)


@dataclass
class PlanDeVuelo:
    """
    Value Object que define la trayectoria completa de un vuelo.
    Contiene waypoints, restricciones de altitud y velocidad, y geocerca de seguridad.
    """
    id: UUID = field(default_factory=uuid4)
    waypoints: List[Waypoint] = field(default_factory=list)
    altitud_minima: float = 30.0     # m (evitar edificios bajos)
    altitud_maxima: float = 120.0    # m (límite regulatorio urbano)
    velocidad_maxima: float = 15.0   # m/s
    distancia_total: float = 0.0     # metros, calculada
    tiempo_estimado: float = 0.0     # segundos, calculado

    def agregar_waypoint(self, waypoint: Waypoint) -> None:
        """Agrega un waypoint y recalcula métricas."""
        self.waypoints.append(waypoint)
        self._recalcular_metricas()

    def _recalcular_metricas(self) -> None:
        """Calcula distancia total y tiempo estimado del plan."""
        if len(self.waypoints) < 2:
            return

        distancia = 0.0
        for i in range(1, len(self.waypoints)):
            w1, w2 = self.waypoints[i-1], self.waypoints[i]
            # Distancia euclidiana 3D simplificada
            import math
            dx = w2.latitud - w1.latitud
            dy = w2.longitud - w1.longitud
            dz = w2.altitud - w1.altitud
            distancia += math.sqrt(dx**2 + dy**2 + dz**2) * 111320  # aprox. metros por grado

        self.distancia_total = distancia
        self.tiempo_estimado = distancia / self.velocidad_maxima if self.velocidad_maxima > 0 else 0

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "waypoints": [
                {
                    "orden": w.orden,
                    "lat": w.latitud,
                    "lng": w.longitud,
                    "alt": w.altitud,
                    "velocidad_max": w.velocidad_max,
                }
                for w in self.waypoints
            ],
            "altitud_minima": self.altitud_minima,
            "altitud_maxima": self.altitud_maxima,
            "velocidad_maxima": self.velocidad_maxima,
            "distancia_total_m": round(self.distancia_total, 2),
            "tiempo_estimado_seg": round(self.tiempo_estimado, 2),
        }