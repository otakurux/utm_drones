"""vuelo_agg.py""" 
from dataclasses import dataclass, field
from typing import List
from uuid import UUID

from ..entities.vuelo import Vuelo
from ..entities.dron import Dron
from ..value_objects.plan_vuelo import PlanDeVuelo
from ..value_objects.geocerca import Geocerca
from ..events.dominio_event import DominioEvent


@dataclass
class AgregadoVuelo:
    """
    Agregado: Vuelo
    Raíz: Vuelo
    Encapsula PlanDeVuelo (Value Object), referencia al Dron asignado y estado actual.
    Solo la raíz (Vuelo) puede ser referenciada desde fuera del agregado.
    """
    raiz: Vuelo = field(default_factory=Vuelo)
    geocerca_seguridad: Geocerca = field(default_factory=Geocerca)

    def __post_init__(self):
        # Inicializar geocerca basada en el plan de vuelo
        if self.raiz.plan_vuelo.waypoints:
            self._actualizar_geocerca()

    def asignar_dron_y_plan(self, dron: Dron, plan: PlanDeVuelo) -> None:
        """
        Método de fábrica del agregado.
        Asigna dron y plan, manteniendo la consistencia del agregado.
        """
        self.raiz.asignar_dron(dron.id)
        self.raiz.establecer_plan(plan)
        self._actualizar_geocerca()

    def _actualizar_geocerca(self) -> None:
        """Recalcula la geocerca de seguridad basada en los waypoints."""
        if not self.raiz.plan_vuelo.waypoints:
            return
        
        # Geocerca que cubre toda la ruta (simplificación)
        waypoints = self.raiz.plan_vuelo.waypoints
        self.geocerca_seguridad = Geocerca(
            tipo="poligonal",
            poligono=[(w.latitud, w.longitud) for w in waypoints],
            altitud_min=self.raiz.plan_vuelo.altitud_minima,
            altitud_max=self.raiz.plan_vuelo.altitud_maxima,
        )

    def iniciar_mision(self, dron: Dron) -> None:
        """
        Inicia la misión completa del agregado.
        Coordina el despegue del dron y el inicio del vuelo.
        """
        if self.raiz.dron_id != dron.id:
            raise ValueError("El dron no coincide con el asignado al vuelo")
        
        # El dron genera su propio evento DronDespego
        dron.despegar(self.raiz.id)
        
        # El vuelo cambia de estado
        self.raiz.iniciar()

    def verificar_conflicto(self, otro_vuelo: 'AgregadoVuelo') -> bool:
        """
        Verifica si este agregado entra en conflicto con otro.
        Analiza intersección de geocercas y proximidad de rutas.
        """
        # Simplificación: verificar proximidad de waypoints
        wp1 = self.raiz.plan_vuelo.waypoints
        wp2 = otro_vuelo.raiz.plan_vuelo.waypoints
        
        if not wp1 or not wp2:
            return False
        
        # Verificar distancia mínima entre waypoints de ambas rutas
        for w1 in wp1:
            for w2 in wp2:
                import math
                distancia = math.sqrt(
                    (w1.latitud - w2.latitud)**2 + 
                    (w1.longitud - w2.longitud)**2
                ) * 111320  # aproximación a metros
                
                alt_diff = abs(w1.altitud - w2.altitud)
                
                if distancia < 15 and alt_diff < 10:  # Umbral de seguridad
                    return True
        
        return False

    def completar_mision(self) -> None:
        """Finaliza la misión del agregado."""
        self.raiz.completar()

    def obtener_eventos(self) -> List[DominioEvent]:
        """Recolecta todos los eventos pendientes del agregado."""
        return self.raiz.obtener_eventos_pendientes()

    def to_dict(self) -> dict:
        return {
            "vuelo": self.raiz.to_dict(),
            "geocerca": self.geocerca_seguridad.to_dict(),
        }