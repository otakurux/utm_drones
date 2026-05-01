"""servicio_gestion_flota""" 
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from uuid import UUID

from ..entities.dron import Dron
from ..entities.entrega import Entrega
from ..enums.estados import EstadoDron, EstadoEntrega
from ..events.dron_mantenimiento import DronMantenimiento


@dataclass
class EstadoFlota:
    """DTO con el estado resumido de la flota."""
    total_drones: int = 0
    disponibles: int = 0
    en_vuelo: int = 0
    cargando: int = 0
    mantenimiento: int = 0
    bateria_promedio: float = 0.0
    entregas_activas: int = 0


class ServicioGestionFlota:
    """
    Servicio de Dominio: Gestión de Flota
    Supervisa disponibilidad, batería y mantenimiento de la flota.
    
    Dependencias: MongoDB (historial), Redis (estado)
    
    Responsabilidades:
    - Monitorear estado de cada dron
    - Detectar batería crítica o fallas de hardware
    - Reasignar entregas pendientes cuando un dron entra en mantenimiento
    - Mantener registro de horas de vuelo y mantenimientos
    """
    
    UMBRAL_BATERIA_CRITICA: float = 15.0      # %
    UMBRAL_BATERIA_BAJA: float = 25.0         # %
    HORAS_MANTENIMIENTO_PREVENTIVO: float = 100.0  # horas de vuelo
    
    def __init__(self):
        self._drones: Dict[str, Dron] = {}
        self._entregas_pendientes_reasignacion: List[Entrega] = []
        self._historial_mantenimiento: Dict[str, List[dict]] = {}
    
    def registrar_dron(self, dron: Dron) -> None:
        """Registra un nuevo dron en la flota."""
        self._drones[str(dron.id)] = dron
        self._historial_mantenimiento[str(dron.id)] = []
    
    def remover_dron(self, dron_id: UUID) -> bool:
        """Remueve un dron de la flota (baja definitiva)."""
        str_id = str(dron_id)
        if str_id in self._drones:
            del self._drones[str_id]
            return True
        return False
    
    def obtener_dron(self, dron_id: UUID) -> Optional[Dron]:
        """Obtiene un dron por su ID."""
        return self._drones.get(str(dron_id))
    
    def obtener_drones_disponibles(self) -> List[Dron]:
        """Retorna todos los drones disponibles para asignación."""
        return [
            d for d in self._drones.values() 
            if d.esta_disponible()
        ]
    
    def obtener_mejor_dron_para_entrega(
        self,
        entrega: Entrega,
        distancia_estimada: float = 0.0,
    ) -> Optional[Dron]:
        """
        Selecciona el mejor dron para una entrega considerando:
        - Disponibilidad
        - Batería suficiente para la distancia
        - Capacidad de carga
        - Proximidad al origen (si se conoce)
        """
        candidatos = self.obtener_drones_disponibles()
        
        if not candidatos:
            return None
        
        # Filtrar por capacidad de carga
        candidatos = [
            d for d in candidatos 
            if d.capacidad_carga_kg >= entrega.paquete.peso_kg
        ]
        
        # Filtrar por autonomía (estimación simple: 150m por % de batería)
        candidatos = [
            d for d in candidatos 
            if (d.bateria_porcentaje * 150) >= distancia_estimada * 1.3  # 30% margen
        ]
        
        if not candidatos:
            return None
        
        # Ordenar por batería (mayor primero) y luego por horas de vuelo (menor primero)
        candidatos.sort(
            key=lambda d: (d.bateria_porcentaje, -d.horas_vuelo_acumuladas),
            reverse=True,
        )
        
        return candidatos[0]
    
    def verificar_estado_drones(self) -> List[DronMantenimiento]:
        """
        Verifica el estado de todos los drones y detecta problemas.
        Se ejecuta periódicamente (ej: cada 30 segundos).
        
        Returns:
            Lista de eventos de mantenimiento generados
        """
        eventos_mantenimiento = []
        
        for dron in self._drones.values():
            # Verificar batería crítica
            if dron.bateria_porcentaje <= self.UMBRAL_BATERIA_CRITICA:
                if dron.estado == EstadoDron.EN_VUELO:
                    # Emergencia: aterrizaje forzado
                    evento = dron.entrar_mantenimiento(
                        motivo="bateria_critica",
                        detalles=f"Batería crítica durante vuelo: {dron.bateria_porcentaje:.1f}%"
                    )
                    eventos_mantenimiento.append(evento)
                elif dron.estado == EstadoDron.DISPONIBLE:
                    # Prevenir vuelo
                    evento = dron.entrar_mantenimiento(
                        motivo="bateria_critica",
                        detalles=f"Batería crítica en tierra: {dron.bateria_porcentaje:.1f}%"
                    )
                    eventos_mantenimiento.append(evento)
            
            # Verificar mantenimiento preventivo por horas de vuelo
            elif dron.horas_vuelo_acumuladas >= self.HORAS_MANTENIMIENTO_PREVENTIVO:
                if dron.estado == EstadoDron.DISPONIBLE:
                    evento = dron.entrar_mantenimiento(
                        motivo="mantenimiento_programado",
                        detalles=f"Horas acumuladas: {dron.horas_vuelo_acumuladas:.1f}"
                    )
                    eventos_mantenimiento.append(evento)
        
        return eventos_mantenimiento
    
    def reasignar_entrega(
        self,
        entrega: Entrega,
        dron_original_id: UUID,
    ) -> Optional[Dron]:
        """
        Reasigna una entrega a otro dron cuando el original entra en mantenimiento.
        """
        # Guardar para reasignación posterior si no hay drones disponibles
        if entrega.estado in [EstadoEntrega.PENDIENTE, EstadoEntrega.ASIGNADA, EstadoEntrega.EN_RUTA]:
            self._entregas_pendientes_reasignacion.append(entrega)
        
        # Buscar nuevo dron
        nuevo_dron = self.obtener_mejor_dron_para_entrega(entrega)
        
        if nuevo_dron:
            # Remover de pendientes si se pudo reasignar
            if entrega in self._entregas_pendientes_reasignacion:
                self._entregas_pendientes_reasignacion.remove(entrega)
            return nuevo_dron
        
        return None
    
    def procesar_reasignaciones_pendientes(self) -> List[Tuple[Entrega, Optional[Dron]]]:
        """
        Intenta reasignar todas las entregas pendientes.
        Se ejecuta periódicamente para limpiar la cola.
        """
        resultados = []
        
        for entrega in self._entregas_pendientes_reasignacion[:]:  # Copia para modificar
            nuevo_dron = self.obtener_mejor_dron_para_entrega(entrega)
            
            if nuevo_dron:
                self._entregas_pendientes_reasignacion.remove(entrega)
            
            resultados.append((entrega, nuevo_dron))
        
        return resultados
    
    def registrar_mantenimiento_completado(self, dron_id: UUID) -> bool:
        """
        Marca un dron como disponible después de mantenimiento.
        """
        dron = self._drones.get(str(dron_id))
        if dron and dron.estado == EstadoDron.MANTENIMIENTO:
            dron.estado = EstadoDron.DISPONIBLE
            dron.bateria_porcentaje = 100.0  # Asume recarga completa en mantenimiento
            
            # Registrar en historial
            self._historial_mantenimiento[str(dron_id)].append({
                "tipo": "completado",
                "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            })
            
            return True
        return False
    
    def obtener_estado_flota(self) -> EstadoFlota:
        """Calcula el estado resumido de toda la flota."""
        if not self._drones:
            return EstadoFlota()
        
        total = len(self._drones)
        baterias = [d.bateria_porcentaje for d in self._drones.values()]
        
        return EstadoFlota(
            total_drones=total,
            disponibles=sum(1 for d in self._drones.values() if d.estado == EstadoDron.DISPONIBLE),
            en_vuelo=sum(1 for d in self._drones.values() if d.estado == EstadoDron.EN_VUELO),
            cargando=sum(1 for d in self._drones.values() if d.estado == EstadoDron.CARGANDO),
            mantenimiento=sum(1 for d in self._drones.values() if d.estado == EstadoDron.MANTENIMIENTO),
            bateria_promedio=sum(baterias) / len(baterias) if baterias else 0.0,
            entregas_activas=sum(1 for d in self._drones.values() if d.estado == EstadoDron.EN_VUELO),
        )
    
    def obtener_historial_dron(self, dron_id: UUID) -> List[dict]:
        """Obtiene el historial de mantenimiento de un dron."""
        return self._historial_mantenimiento.get(str(dron_id), [])
    
    def obtener_alertas(self) -> List[dict]:
        """
        Genera alertas operativas para el dashboard.
        """
        alertas = []
        
        for dron in self._drones.values():
            # Alerta batería baja
            if self.UMBRAL_BATERIA_CRITICA < dron.bateria_porcentaje <= self.UMBRAL_BATERIA_BAJA:
                alertas.append({
                    "tipo": "bateria_baja",
                    "dron_id": str(dron.id),
                    "numero_serie": dron.numero_serie,
                    "nivel_bateria": dron.bateria_porcentaje,
                    "mensaje": f"Dron {dron.numero_serie} tiene batería baja ({dron.bateria_porcentaje:.1f}%)",
                    "severidad": "media",
                })
            
            # Alerta mantenimiento próximo
            horas_restantes = self.HORAS_MANTENIMIENTO_PREVENTIVO - dron.horas_vuelo_acumuladas
            if 0 < horas_restantes <= 10:
                alertas.append({
                    "tipo": "mantenimiento_proximo",
                    "dron_id": str(dron.id),
                    "numero_serie": dron.numero_serie,
                    "horas_restantes": horas_restantes,
                    "mensaje": f"Dron {dron.numero_serie} requiere mantenimiento en {horas_restantes:.1f} horas",
                    "severidad": "baja",
                })
        
        # Alerta reasignaciones pendientes
        if self._entregas_pendientes_reasignacion:
            alertas.append({
                "tipo": "reasignaciones_pendientes",
                "cantidad": len(self._entregas_pendientes_reasignacion),
                "mensaje": f"{len(self._entregas_pendientes_reasignacion)} entregas esperando reasignación",
                "severidad": "alta" if len(self._entregas_pendientes_reasignacion) > 3 else "media",
            })
        
        return alertas