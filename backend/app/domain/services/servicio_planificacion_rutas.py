"""servicio_planificacion_rutas""" 
import math
import heapq
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set
from uuid import UUID

from ..entities.dron import Dron
from ..entities.zona_restringida import ZonaRestringida
from ..value_objects.plan_vuelo import PlanDeVuelo, Waypoint
from ..value_objects.geocerca import Geocerca


@dataclass
class NodoAStar:
    """Nodo interno para el algoritmo A*."""
    lat: float
    lng: float
    alt: float
    g: float = 0.0          # Costo acumulado desde origen
    h: float = 0.0          # Heurística (distancia estimada a destino)
    padre: Optional['NodoAStar'] = None
    
    @property
    def f(self) -> float:
        return self.g + self.h
    
    def __lt__(self, otro: 'NodoAStar') -> bool:
        return self.f < otro.f
    
    def __eq__(self, otro: object) -> bool:
        if not isinstance(otro, NodoAStar):
            return False
        return (self.lat, self.lng, self.alt) == (otro.lat, otro.lng, otro.alt)
    
    def __hash__(self) -> int:
        return hash((round(self.lat, 6), round(self.lng, 6), round(self.alt, 1)))


class ServicioPlanificacionRutas:
    """
    Servicio de Dominio: Planificación de Rutas
    Calcula trayectorias óptimas evitando colisiones y zonas restringidas.
    Implementa algoritmo A* geoespacial en 3D.
    
    Dependencias: MongoDB (zonas), Redis (tráfico actual)
    """
    
    # Constantes del sistema
    VELOCIDAD_CRUCERO: float = 12.0          # m/s (43.2 km/h)
    ALTITUD_SEGURA_MIN: float = 30.0         # m (sobre edificios bajos)
    ALTITUD_SEGURA_MAX: float = 120.0        # m (límite regulatorio)
    SEPARACION_VERTICAL: float = 10.0        # m entre drones
    RESOLUCION_GRILLA: float = 0.0005        # ~55m en latitud (ajustable)
    RESOLUCION_ALTITUD: float = 15.0         # m entre niveles de vuelo
    PESO_ZONA_RESTRINGIDA: float = float('inf')
    PESO_CONGESTION: float = 1.5
    PESO_CAMBIO_ALTITUD: float = 1.2
    PESO_DISTANCIA: float = 1.0
    
    def __init__(self, zonas_restringidas: List[ZonaRestringida] = None):
        self.zonas_restringidas = zonas_restringidas or []
        self._cache_zonas_activas: List[ZonaRestringida] = []
    
    def _obtener_zonas_activas(self) -> List[ZonaRestringida]:
        """Filtra solo zonas vigentes en este momento."""
        self._cache_zonas_activas = [z for z in self.zonas_restringidas if z.esta_vigente()]
        return self._cache_zonas_activas
    
    def _heuristica(self, nodo: NodoAStar, destino: Tuple[float, float, float]) -> float:
        """
        Distancia euclidiana 3D estimada hasta el destino.
        Usa aproximación de metros por grado de latitud/longitud.
        """
        lat_diff = (destino[0] - nodo.lat) * 111320  # metros por grado lat
        lng_diff = (destino[1] - nodo.lng) * 111320 * math.cos(math.radians(nodo.lat))
        alt_diff = destino[2] - nodo.alt
        
        return math.sqrt(lat_diff**2 + lng_diff**2 + alt_diff**2)
    
    def _distancia_entre_nodos(self, n1: NodoAStar, n2: NodoAStar) -> float:
        """Distancia real en metros entre dos nodos."""
        lat_diff = (n2.lat - n1.lat) * 111320
        lng_diff = (n2.lng - n1.lng) * 111320 * math.cos(math.radians(n1.lat))
        alt_diff = n2.alt - n1.alt
        
        return math.sqrt(lat_diff**2 + lng_diff**2 + alt_diff**2)
    
    def _es_nodo_valido(self, lat: float, lng: float, alt: float) -> bool:
        """
        Verifica si un punto es válido para el vuelo:
        - Dentro de límites de altitud
        - Fuera de zonas restringidas
        """
        # Verificar límites de altitud
        if not (self.ALTITUD_SEGURA_MIN <= alt <= self.ALTITUD_SEGURA_MAX):
            return False
        
        # Verificar zonas restringidas
        for zona in self._obtener_zonas_activas():
            if zona.contiene_punto(lat, lng, alt):
                return False
        
        return True
    
    def _calcular_costo(self, actual: NodoAStar, vecino: NodoAStar) -> float:
        """
        Calcula el costo de moverse de 'actual' a 'vecino'.
        Incluye penalizaciones por congestión, cambios de altitud, etc.
        """
        costo = self._distancia_entre_nodos(actual, vecino) * self.PESO_DISTANCIA
        
        # Penalización por cambio brusco de altitud
        alt_diff = abs(vecino.alt - actual.alt)
        if alt_diff > self.SEPARACION_VERTICAL:
            costo *= self.PESO_CAMBIO_ALTITUD
        
        # Penalización por proximidad a zonas restringidas (margen de seguridad)
        for zona in self._obtener_zonas_activas():
            # Punto medio entre nodos
            mid_lat = (actual.lat + vecino.lat) / 2
            mid_lng = (actual.lng + vecino.lng) / 2
            mid_alt = (actual.alt + vecino.alt) / 2
            
            # Si está cerca de zona restringida (margen de 20m)
            if zona.contiene_punto(mid_lat, mid_lng, mid_alt):
                costo = self.PESO_ZONA_RESTRINGIDA
                break
            # Penalización por proximidad (margen de seguridad de 50m)
            elif self._distancia_a_zona(mid_lat, mid_lng, mid_alt, zona) < 50:
                costo *= 2.0
        
        return costo
    
    def _distancia_a_zona(self, lat: float, lng: float, alt: float, zona: ZonaRestringida) -> float:
        """Calcula distancia aproximada desde un punto al borde de una zona."""
        # Simplificación: si está fuera, retornar distancia al centro
        if not zona.coordenadas:
            return float('inf')
        
        centro_lat = sum(c[0] for c in zona.coordenadas) / len(zona.coordenadas)
        centro_lng = sum(c[1] for c in zona.coordenadas) / len(zona.coordenadas)
        
        lat_diff = (lat - centro_lat) * 111320
        lng_diff = (lng - centro_lng) * 111320 * math.cos(math.radians(lat))
        
        return math.sqrt(lat_diff**2 + lng_diff**2)
    
    def _generar_vecinos(self, nodo: NodoAStar) -> List[NodoAStar]:
        """
        Genera nodos vecinos en 3D:
        - 8 direcciones horizontales (N, NE, E, SE, S, SW, W, NW)
        - 2 niveles de altitud (subir, bajar) cuando es necesario
        """
        vecinos = []
        res = self.RESOLUCION_GRILLA
        res_alt = self.RESOLUCION_ALTITUD
        
        # Movimientos horizontales
        movimientos = [
            (res, 0), (res, res), (0, res), (-res, res),
            (-res, 0), (-res, -res), (0, -res), (res, -res)
        ]
        
        for dlat, dlng in movimientos:
            nuevo_lat = nodo.lat + dlat
            nuevo_lng = nodo.lng + dlng
            
            # Mantener altitud actual
            if self._es_nodo_valido(nuevo_lat, nuevo_lng, nodo.alt):
                vecinos.append(NodoAStar(nuevo_lat, nuevo_lng, nodo.alt))
            
            # Subir
            nuevo_alt_up = nodo.alt + res_alt
            if self._es_nodo_valido(nuevo_lat, nuevo_lng, nuevo_alt_up):
                vecinos.append(NodoAStar(nuevo_lat, nuevo_lng, nuevo_alt_up))
            
            # Bajar
            nuevo_alt_down = nodo.alt - res_alt
            if self._es_nodo_valido(nuevo_lat, nuevo_lng, nuevo_alt_down):
                vecinos.append(NodoAStar(nuevo_lat, nuevo_lng, nuevo_alt_down))
        
        # Movimientos verticales puros (hover y cambio de nivel)
        for alt_offset in [res_alt, -res_alt]:
            nueva_alt = nodo.alt + alt_offset
            if self._es_nodo_valido(nodo.lat, nodo.lng, nueva_alt):
                vecinos.append(NodoAStar(nodo.lat, nodo.lng, nueva_alt))
        
        return vecinos
    
    def _reconstruir_ruta(self, nodo_final: NodoAStar) -> List[Waypoint]:
        """Reconstruye la ruta desde el nodo final siguiendo los padres."""
        waypoints = []
        nodo_actual = nodo_final
        
        while nodo_actual is not None:
            waypoints.append(Waypoint(
                orden=0,  # Se asignará después
                latitud=nodo_actual.lat,
                longitud=nodo_actual.lng,
                altitud=nodo_actual.alt,
                velocidad_max=self.VELOCIDAD_CRUCERO,
            ))
            nodo_actual = nodo_actual.padre
        
        # Invertir y asignar órdenes
        waypoints.reverse()
        for i, wp in enumerate(waypoints):
            wp.orden = i
        
        return waypoints
    
    def calcular_ruta_optima(
        self,
        origen: Tuple[float, float, float],
        destino: Tuple[float, float, float],
        dron: Optional[Dron] = None,
        zonas_restringidas: Optional[List[ZonaRestringida]] = None,
    ) -> PlanDeVuelo:
        """
        Calcula la ruta óptima usando A* geoespacial.
        
        Args:
            origen: (lat, lng, alt) punto de partida
            destino: (lat, lng, alt) punto de llegada
            dron: Dron asignado (para verificar batería)
            zonas_restringidas: Lista de zonas a evitar
        
        Returns:
            PlanDeVuelo con waypoints optimizados
        
        Raises:
            ValueError: Si no se encuentra ruta válida
        """
        if zonas_restringidas:
            self.zonas_restringidas = zonas_restringidas
        
        # Verificar que origen y destino sean válidos
        if not self._es_nodo_valido(*origen):
            raise ValueError(f"Origen {origen} está en zona restringida o fuera de límites")
        if not self._es_nodo_valido(*destino):
            raise ValueError(f"Destino {destino} está en zona restringida o fuera de límites")
        
        # Verificar batería del dron si está disponible
        if dron:
            distancia_estimada = self._heuristica(
                NodoAStar(origen[0], origen[1], origen[2]), 
                destino
            )
            autonomia_estimada = (dron.bateria_porcentaje / 100.0) * self._estimar_autonomia(dron)
            if distancia_estimada > autonomia_estimada * 0.8:  # 20% margen de seguridad
                raise ValueError(
                    f"Batería insuficiente. Distancia: {distancia_estimada:.0f}m, "
                    f"Autonomía: {autonomia_estimada:.0f}m"
                )
        
        # Inicializar A*
        nodo_inicial = NodoAStar(origen[0], origen[1], origen[2])
        nodo_objetivo = NodoAStar(destino[0], destino[1], destino[2])
        
        # Colas de A*
        abierta: List[Tuple[float, NodoAStar]] = []
        heapq.heappush(abierta, (0.0, nodo_inicial))
        
        cerrada: Set[NodoAStar] = set()
        
        # Para reconstrucción rápida
        g_scores: dict = {nodo_inicial: 0.0}
        
        max_iteraciones = 10000
        iteraciones = 0
        
        while abierta and iteraciones < max_iteraciones:
            iteraciones += 1
            
            _, nodo_actual = heapq.heappop(abierta)
            
            # Verificar si llegamos al destino (con tolerancia)
            distancia_a_destino = self._distancia_entre_nodos(nodo_actual, nodo_objetivo)
            if distancia_a_destino < self.RESOLUCION_GRILLA * 111320:
                # Reconstruir y retornar
                waypoints = self._reconstruir_ruta(nodo_actual)
                plan = PlanDeVuelo(
                    waypoints=waypoints,
                    altitud_minima=self.ALTITUD_SEGURA_MIN,
                    altitud_maxima=self.ALTITUD_SEGURA_MAX,
                    velocidad_maxima=self.VELOCIDAD_CRUCERO,
                )
                plan._recalcular_metricas()
                return plan
            
            if nodo_actual in cerrada:
                continue
            
            cerrada.add(nodo_actual)
            
            # Generar vecinos
            for vecino in self._generar_vecinos(nodo_actual):
                if vecino in cerrada:
                    continue
                
                costo_movimiento = self._calcular_costo(nodo_actual, vecino)
                
                if costo_movimiento == float('inf'):
                    continue
                
                g_tentativo = g_scores.get(nodo_actual, float('inf')) + costo_movimiento
                
                if g_tentativo < g_scores.get(vecino, float('inf')):
                    vecino.padre = nodo_actual
                    vecino.g = g_tentativo
                    vecino.h = self._heuristica(vecino, destino)
                    g_scores[vecino] = g_tentativo
                    heapq.heappush(abierta, (vecino.f, vecino))
        
        raise ValueError(
            f"No se encontró ruta válida después de {iteraciones} iteraciones. "
            f"Posiblemente el destino está completamente bloqueado por zonas restringidas."
        )
    
    def _estimar_autonomia(self, dron: Dron) -> float:
        """
        Estima la autonomía del dron en metros basado en modelo y batería.
        Simplificación: 100m por cada 1% de batería para drones estándar.
        """
        # Estimación básica, se puede refinar con modelos específicos
        return dron.bateria_porcentaje * 150  # 150m por % de batería
    
    def verificar_ruta_segura(
        self,
        plan: PlanDeVuelo,
        trafico_activo: Optional[List[Tuple[UUID, List[Waypoint]]]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Verifica si una ruta planificada es segura considerando tráfico actual.
        
        Args:
            plan: Plan de vuelo a verificar
            trafico_activo: Lista de (dron_id, waypoints) de drones en vuelo
        
        Returns:
            (es_segura, lista_de_alertas)
        """
        alertas = []
        
        # Verificar cada waypoint contra zonas restringidas
        for i, wp in enumerate(plan.waypoints):
            for zona in self._obtener_zonas_activas():
                if zona.contiene_punto(wp.latitud, wp.longitud, wp.altitud):
                    alertas.append(
                        f"Waypoint {i} ({wp.latitud}, {wp.longitud}, {wp.altitud}m) "
                        f"intersecta zona restringida {zona.codigo}"
                    )
        
        # Verificar contra tráfico activo
        if trafico_activo:
            for dron_id, waypoints_otro in trafico_activo:
                for wp1 in plan.waypoints:
                    for wp2 in waypoints_otro:
                        distancia = self._distancia_waypoints(wp1, wp2)
                        if distancia < 15:  # 15m separación mínima
                            alertas.append(
                                f"Conflicto potencial con dron {dron_id}: "
                                f"distancia {distancia:.1f}m en "
                                f"({wp1.latitud}, {wp1.longitud})"
                            )
        
        return len(alertas) == 0, alertas
    
    def _distancia_waypoints(self, w1: Waypoint, w2: Waypoint) -> float:
        """Distancia en metros entre dos waypoints."""
        lat_diff = (w2.latitud - w1.latitud) * 111320
        lng_diff = (w2.longitud - w1.longitud) * 111320 * math.cos(math.radians(w1.latitud))
        alt_diff = w2.altitud - w1.altitud
        return math.sqrt(lat_diff**2 + lng_diff**2 + alt_diff**2)
    
    def generar_geocerca_ruta(self, plan: PlanDeVuelo, radio_metros: float = 20.0) -> Geocerca:
        """
        Genera una geocerca de seguridad alrededor de toda la ruta.
        """
        if not plan.waypoints:
            return Geocerca(tipo="circular", radio_metros=radio_metros)
        
        # Crear polígono que envuelve la ruta con margen
        coords = [(w.latitud, w.longitud) for w in plan.waypoints]
        
        return Geocerca(
            tipo="poligonal",
            poligono=coords,
            radio_metros=radio_metros,
            altitud_min=plan.altitud_minima - 10,
            altitud_max=plan.altitud_maxima + 10,
        )