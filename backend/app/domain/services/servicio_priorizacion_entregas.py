"""servicio_priorizacion_entregas""" 
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
from uuid import UUID

from ..entities.entrega import Entrega
from ..enums.estados import EstadoEntrega, TipoEntrega


@dataclass
class EntregaPriorizada:
    """DTO interno para manejar entregas con score calculado."""
    entrega: Entrega
    score: float
    tiempo_espera_segundos: float


class ServicioPriorizacionEntregas:
    """
    Servicio de Dominio: Priorización de Entregas
    Asigna puntajes de prioridad a pedidos según tipo, tiempo de espera y congestión.
    
    Dependencias: Redis (cola de prioridad)
    
    Reglas de prioridad base:
    - Medicina = 10
    - Alimentos = 7  
    - Farmacia = 5
    - General = 1
    
    El score aumenta con el tiempo de espera (+1 cada 5 minutos).
    """
    
    FACTOR_TIEMPO_ESPERA: float = 1.0      # +1 punto cada 5 minutos
    FACTOR_CONGESTION: float = 0.5          # Penalización por congestión aérea
    FACTOR_PESO: float = 0.1                # Penalización por peso del paquete
    FACTOR_DISTANCIA: float = 0.001         # Penalización por distancia estimada
    
    def __init__(self):
        self._cola_prioridad: List[EntregaPriorizada] = []
        self._entregas_index: dict = {}       # Para búsqueda rápida por ID
    
    def calcular_score(
        self,
        entrega: Entrega,
        nivel_congestion: float = 0.0,       # 0.0 - 1.0 (porcentaje de congestión)
        distancia_estimada: float = 0.0,      # metros
    ) -> float:
        """
        Calcula el score final de prioridad para una entrega.
        
        Fórmula:
        score = prioridad_base + factor_tiempo - penalizacion_congestion 
                - penalizacion_peso - penalizacion_distancia
        """
        # Prioridad base según tipo
        prioridad_base = float(entrega.tipo.prioridad)
        
        # Factor tiempo de espera
        minutos_espera = entrega.calcular_score_prioridad() - prioridad_base
        factor_tiempo = minutos_espera * self.FACTOR_TIEMPO_ESPERA
        
        # Penalización por congestión aérea en la zona
        penalizacion_congestion = nivel_congestion * 5 * self.FACTOR_CONGESTION
        
        # Penalización por peso (drones pequeños no pueden cargar mucho)
        peso_kg = entrega.paquete.peso_kg
        penalizacion_peso = peso_kg * self.FACTOR_PESO
        
        # Penalización por distancia (preferir entregas cortas en horas pico)
        penalizacion_distancia = distancia_estimada * self.FACTOR_DISTANCIA
        
        score_final = (
            prioridad_base 
            + factor_tiempo 
            - penalizacion_congestion 
            - penalizacion_peso 
            - penalizacion_distancia
        )
        
        return max(0.0, score_final)  # Score no puede ser negativo
    
    def encolar_entrega(
        self,
        entrega: Entrega,
        nivel_congestion: float = 0.0,
        distancia_estimada: float = 0.0,
    ) -> EntregaPriorizada:
        """
        Agrega una entrega a la cola de prioridad con su score calculado.
        """
        if entrega.estado != EstadoEntrega.PENDIENTE:
            raise ValueError(f"Solo se pueden encolar entregas PENDIENTES. Estado: {entrega.estado}")
        
        score = self.calcular_score(entrega, nivel_congestion, distancia_estimada)
        
        tiempo_espera = (time.time() - entrega.fecha_creacion.timestamp())
        
        priorizada = EntregaPriorizada(
            entrega=entrega,
            score=score,
            tiempo_espera_segundos=tiempo_espera,
        )
        
        self._cola_prioridad.append(priorizada)
        self._entregas_index[str(entrega.id)] = priorizada
        
        # Reordenar por score descendente
        self._cola_prioridad.sort(key=lambda x: x.score, reverse=True)
        
        return priorizada
    
    def obtener_siguiente_entrega(self) -> Optional[Entrega]:
        """
        Retorna la entrega con mayor prioridad y la remueve de la cola.
        """
        while self._cola_prioridad:
            priorizada = self._cola_prioridad.pop(0)
            
            # Verificar que sigue pendiente
            if priorizada.entrega.estado == EstadoEntrega.PENDIENTE:
                del self._entregas_index[str(priorizada.entrega.id)]
                return priorizada.entrega
            
            # Si ya no está pendiente, descartar
            if str(priorizada.entrega.id) in self._entregas_index:
                del self._entregas_index[str(priorizada.entrega.id)]
        
        return None
    
    def actualizar_scores(self, congestiones: dict = None) -> None:
        """
        Recalcula todos los scores considerando el tiempo transcurrido.
        congestiones: dict {entrega_id: nivel_congestion}
        """
        congestiones = congestiones or {}
        
        for priorizada in self._cola_prioridad:
            entrega = priorizada.entrega
            
            # Solo actualizar si sigue pendiente
            if entrega.estado != EstadoEntrega.PENDIENTE:
                continue
            
            congestion = congestiones.get(str(entrega.id), 0.0)
            nuevo_score = self.calcular_score(entrega, congestion)
            
            priorizada.score = nuevo_score
            priorizada.tiempo_espera_segundos = (
                time.time() - entrega.fecha_creacion.timestamp()
            )
        
        # Reordenar
        self._cola_prioridad.sort(key=lambda x: x.score, reverse=True)
    
    def obtener_cola_ordenada(self) -> List[dict]:
        """Retorna la cola actual ordenada por prioridad (para dashboard)."""
        return [
            {
                "entrega_id": str(p.entrega.id),
                "numero_pedido": p.entrega.numero_pedido,
                "tipo": p.entrega.tipo.value,
                "score": round(p.score, 2),
                "tiempo_espera_min": round(p.tiempo_espera_segundos / 60, 1),
                "prioridad_base": p.entrega.tipo.prioridad,
            }
            for p in self._cola_prioridad
            if p.entrega.estado == EstadoEntrega.PENDIENTE
        ]
    
    def remover_entrega(self, entrega_id: UUID) -> bool:
        """Remueve una entrega específica de la cola."""
        str_id = str(entrega_id)
        if str_id in self._entregas_index:
            priorizada = self._entregas_index[str_id]
            self._cola_prioridad.remove(priorizada)
            del self._entregas_index[str_id]
            return True
        return False
    
    def cantidad_pendientes(self) -> int:
        """Cantidad de entregas pendientes en la cola."""
        return sum(
            1 for p in self._cola_prioridad 
            if p.entrega.estado == EstadoEntrega.PENDIENTE
        )
    
    def hay_entregas_criticas(self) -> bool:
        """Verifica si hay entregas de medicina esperando."""
        return any(
            p.entrega.tipo == TipoEntrega.MEDICINA 
            and p.entrega.estado == EstadoEntrega.PENDIENTE
            for p in self._cola_prioridad
        )