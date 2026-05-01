"""servicio_deteccion_conflictos""" 
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from uuid import UUID

from ..entities.vuelo import Vuelo
from ..entities.dron import Dron
from ..value_objects.plan_vuelo import Waypoint
from ..events.conflicto_detectado import ConflictoDetectado


@dataclass
class Posicion3D:
    """Representa una posición en el espacio aéreo."""
    lat: float
    lng: float
    alt: float
    timestamp: float  # timestamp Unix
    
    def distancia_a(self, otra: 'Posicion3D') -> float:
        """Distancia euclidiana 3D en metros."""
        lat_diff = (self.lat - otra.lat) * 111320
        lng_diff = (self.lng - otra.lng) * 111320 * math.cos(math.radians(self.lat))
        alt_diff = self.alt - otra.alt
        return math.sqrt(lat_diff**2 + lng_diff**2 + alt_diff**2)


@dataclass
class RutaActiva:
    """Representa una ruta en vuelo para análisis de conflictos."""
    vuelo_id: UUID
    dron_id: UUID
    waypoints: List[Waypoint]
    prioridad: int  # Prioridad de la entrega asociada
    posicion_actual: Posicion3D
    velocidad: float  # m/s
    waypoint_actual: int


class ServicioDeteccionConflictos:
    """
    Servicio de Dominio: Detección de Conflictos
    Analiza intersección de rutas en tiempo real usando geometría 3D esférica.
    
    Dependencias: Redis (posiciones), PlanDeVuelo activos
    
    Umbral de seguridad:
    - Horizontal: 15 metros
    - Vertical: 10 metros
    - Temporal: 60 segundos (ventana de predicción)
    """
    
    UMBRAL_HORIZONTAL: float = 15.0      # metros
    UMBRAL_VERTICAL: float = 10.0        # metros
    VENTANA_PREDICCION: float = 60.0     # segundos hacia adelante
    INTERVALO_VERIFICACION: float = 0.5  # segundos (500ms)
    
    def __init__(self):
        self._rutas_activas: Dict[str, RutaActiva] = {}
        self._conflictos_detectados: List[ConflictoDetectado] = []
    
    def registrar_ruta(self, ruta: RutaActiva) -> None:
        """Registra una nueva ruta activa para monitoreo."""
        self._rutas_activas[str(ruta.vuelo_id)] = ruta
    
    def remover_ruta(self, vuelo_id: UUID) -> None:
        """Remueve una ruta que ya no está activa."""
        str_id = str(vuelo_id)
        if str_id in self._rutas_activas:
            del self._rutas_activas[str_id]
    
    def actualizar_posicion(
        self,
        vuelo_id: UUID,
        lat: float,
        lng: float,
        alt: float,
        velocidad: float,
        timestamp: float,
    ) -> None:
        """Actualiza la posición actual de una ruta en monitoreo."""
        str_id = str(vuelo_id)
        if str_id in self._rutas_activas:
            self._rutas_activas[str_id].posicion_actual = Posicion3D(
                lat, lng, alt, timestamp
            )
            self._rutas_activas[str_id].velocidad = velocidad
    
    def detectar_conflictos(self) -> List[ConflictoDetectado]:
        """
        Analiza todas las rutas activas y detecta conflictos potenciales.
        Se ejecuta cada 500ms.
        
        Algoritmo:
        1. Para cada par de rutas activas
        2. Predecir posiciones en los próximos 60 segundos
        3. Calcular distancia mínima entre trayectorias predichas
        4. Si distancia < umbral, generar evento de conflicto
        """
        self._conflictos_detectados = []
        rutas_list = list(self._rutas_activas.values())
        
        for i in range(len(rutas_list)):
            for j in range(i + 1, len(rutas_list)):
                ruta_a = rutas_list[i]
                ruta_b = rutas_list[j]
                
                conflicto = self._analizar_par_rutas(ruta_a, ruta_b)
                if conflicto:
                    self._conflictos_detectados.append(conflicto)
        
        return self._conflictos_detectados
    
    def _analizar_par_rutas(
        self,
        ruta_a: RutaActiva,
        ruta_b: RutaActiva,
    ) -> Optional[ConflictoDetectado]:
        """
        Analiza un par de rutas para detectar conflicto.
        Usa predicción de trayectorias basada en waypoints restantes.
        """
        # Obtener waypoints restantes para ambas rutas
        wp_restantes_a = ruta_a.waypoints[ruta_a.waypoint_actual:]
        wp_restantes_b = ruta_b.waypoints[ruta_b.waypoint_actual:]
        
        if not wp_restantes_a or not wp_restantes_b:
            return None
        
        # Predecir posiciones en ventana de tiempo
        tiempo_actual = ruta_a.posicion_actual.timestamp
        
        for t_offset in [i * self.INTERVALO_VERIFICACION 
                        for i in range(int(self.VENTANA_PREDICCION / self.INTERVALO_VERIFICACION))]:
            
            tiempo_futuro = tiempo_actual + t_offset
            
            pos_a = self._predecir_posicion(ruta_a, tiempo_futuro, wp_restantes_a)
            pos_b = self._predecir_posicion(ruta_b, tiempo_futuro, wp_restantes_b)
            
            if pos_a is None or pos_b is None:
                continue
            
            distancia = pos_a.distancia_a(pos_b)
            
            # Verificar umbral de seguridad
            if distancia < math.sqrt(self.UMBRAL_HORIZONTAL**2 + self.UMBRAL_VERTICAL**2):
                # Calcular punto de intersección aproximado
                punto_interseccion = self._calcular_punto_interseccion(pos_a, pos_b)
                
                return ConflictoDetectado(
                    aggregate_id=ruta_a.vuelo_id,
                    vuelo_a_id=ruta_a.vuelo_id,
                    vuelo_b_id=ruta_b.vuelo_id,
                    dron_a_id=ruta_a.dron_id,
                    dron_b_id=ruta_b.dron_id,
                    punto_interseccion_lat=punto_interseccion[0],
                    punto_interseccion_lng=punto_interseccion[1],
                    punto_interseccion_alt=punto_interseccion[2],
                    distancia_estimada=distancia,
                    tiempo_para_conflicto=t_offset,
                    severidad="alta" if distancia < 10 else "media",
                )
        
        return None
    
    def _predecir_posicion(
        self,
        ruta: RutaActiva,
        tiempo_futuro: float,
        waypoints_restantes: List[Waypoint],
    ) -> Optional[Posicion3D]:
        """
        Predice la posición de un dron en un tiempo futuro basado en su ruta.
        Interpola linealmente entre waypoints.
        """
        if not waypoints_restantes:
            return None
        
        # Tiempo transcurrido desde posición actual
        delta_t = tiempo_futuro - ruta.posicion_actual.timestamp
        
        # Distancia que recorrerá en ese tiempo
        distancia_recorrer = ruta.velocidad * delta_t
        
        # Recorrer waypoints acumulando distancia
        distancia_acumulada = 0.0
        pos_actual = ruta.posicion_actual
        
        for wp in waypoints_restantes:
            # Distancia al siguiente waypoint
            lat_diff = (wp.latitud - pos_actual.lat) * 111320
            lng_diff = (wp.longitud - pos_actual.lng) * 111320 * math.cos(math.radians(pos_actual.lat))
            alt_diff = wp.altitud - pos_actual.alt
            distancia_wp = math.sqrt(lat_diff**2 + lng_diff**2 + alt_diff**2)
            
            if distancia_acumulada + distancia_wp >= distancia_recorrer:
                # Interpolar posición en este segmento
                ratio = (distancia_recorrer - distancia_acumulada) / distancia_wp if distancia_wp > 0 else 0
                
                return Posicion3D(
                    lat=pos_actual.lat + (wp.latitud - pos_actual.lat) * ratio,
                    lng=pos_actual.lng + (wp.longitud - pos_actual.lng) * ratio,
                    alt=pos_actual.alt + (wp.altitud - pos_actual.alt) * ratio,
                    timestamp=tiempo_futuro,
                )
            
            distancia_acumulada += distancia_wp
            pos_actual = Posicion3D(wp.latitud, wp.longitud, wp.altitud, tiempo_futuro)
        
        # Si llegó al final de la ruta
        return pos_actual
    
    def _calcular_punto_interseccion(
        self,
        pos_a: Posicion3D,
        pos_b: Posicion3D,
    ) -> Tuple[float, float, float]:
        """Calcula el punto medio entre dos posiciones como punto de intersección."""
        return (
            (pos_a.lat + pos_b.lat) / 2,
            (pos_a.lng + pos_b.lng) / 2,
            (pos_a.alt + pos_b.alt) / 2,
        )
    
    def resolver_conflicto(
        self,
        conflicto: ConflictoDetectado,
        prioridad_a: int,
        prioridad_b: int,
    ) -> Tuple[UUID, str]:
        """
        Determina qué dron debe ceder basado en prioridad.
        
        Returns:
            (dron_id_que_debe_ceder, accion_recomendada)
        """
        if prioridad_a > prioridad_b:
            # A tiene mayor prioridad, B debe ceder
            return conflicto.dron_b_id, self._determinar_accion(conflicto, "b")
        elif prioridad_b > prioridad_a:
            # B tiene mayor prioridad, A debe ceder
            return conflicto.dron_a_id, self._determinar_accion(conflicto, "a")
        else:
            # Misma prioridad: el que está más lejos de su destino cede
            # (simplificación, se puede usar otro criterio)
            return conflicto.dron_a_id, "ESPERAR"
    
    def _determinar_accion(
        self,
        conflicto: ConflictoDetectado,
        dron_objetivo: str,
    ) -> str:
        """
        Determina la acción recomendada para resolver el conflicto.
        """
        altitud_conflicto = conflicto.punto_interseccion_alt
        
        if altitud_conflicto + 20 <= 120:  # Si hay espacio para subir
            return "ASCENDER +20m"
        elif altitud_conflicto - 20 >= 30:  # Si hay espacio para bajar
            return "DESCENDER -20m"
        else:
            return "ESPERAR"
    
    def obtener_estadisticas(self) -> dict:
        """Retorna estadísticas del servicio para monitoreo."""
        return {
            "rutas_monitoreadas": len(self._rutas_activas),
            "conflictos_ultima_verificacion": len(self._conflictos_detectados),
            "umbral_horizontal": self.UMBRAL_HORIZONTAL,
            "umbral_vertical": self.UMBRAL_VERTICAL,
            "ventana_prediccion_seg": self.VENTANA_PREDICCION,
        }