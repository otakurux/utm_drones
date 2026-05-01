"""redis_pubsub""" 
import json
from typing import Callable, Optional, List, Dict, Any
from uuid import UUID

from ...domain.events.dominio_event import DominioEvent
from ...domain.events.dron_despego import DronDespego
from ...domain.events.posicion_actualizada import PosicionActualizada
from ...domain.events.conflicto_detectado import ConflictoDetectado
from ...domain.events.entrega_completada import EntregaCompletada
from ...domain.events.dron_mantenimiento import DronMantenimiento
from ..persistence.redis_client import RedisClient


class RedisPubSub:
    """
    Sistema de mensajería Publish/Subscribe basado en Redis.
    Permite comunicación asíncrona entre módulos del sistema.
    
    Canales:
    - utm:events        : Eventos de dominio generales
    - utm:posiciones    : Actualizaciones de posición (alta frecuencia)
    - utm:alertas       : Alertas y conflictos (crítico)
    - utm:dashboard     : Eventos para el frontend
    """
    
    CANAL_EVENTOS = "utm:events"
    CANAL_POSICIONES = "utm:posiciones"
    CANAL_ALERTAS = "utm:alertas"
    CANAL_DASHBOARD = "utm:dashboard"
    
    def __init__(self, redis_client: RedisClient):
        self._redis = redis_client
        self._pubsub = None
        self._handlers: Dict[str, List[Callable]] = {
            self.CANAL_EVENTOS: [],
            self.CANAL_POSICIONES: [],
            self.CANAL_ALERTAS: [],
            self.CANAL_DASHBOARD: [],
        }
        self._running = False
    
    async def connect(self) -> None:
        """Inicializa la conexión Pub/Sub."""
        self._pubsub = self._redis.client.pubsub()
    
    async def disconnect(self) -> None:
        """Cierra la conexión Pub/Sub."""
        self._running = False
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
    
    # ============================================================
    # PUBLICACIÓN
    # ============================================================
    
    async def publicar_evento(self, evento: DominioEvent) -> int:
        """
        Publica un evento de dominio en el canal correspondiente.
        Retorna el número de suscriptores que recibieron el mensaje.
        """
        canal = self._determinar_canal(evento)
        mensaje = json.dumps(evento.to_dict())
        return await self._redis.client.publish(canal, mensaje)
    
    async def publicar_posicion(self, evento: PosicionActualizada) -> int:
        """Publica actualización de posición en canal dedicado."""
        mensaje = json.dumps(evento.to_dict())
        return await self._redis.client.publish(self.CANAL_POSICIONES, mensaje)
    
    async def publicar_alerta(self, evento: ConflictoDetectado) -> int:
        """Publica alerta de conflicto en canal prioritario."""
        mensaje = json.dumps(evento.to_dict())
        # Publicar tanto en alertas como en dashboard
        await self._redis.client.publish(self.CANAL_ALERTAS, mensaje)
        return await self._redis.client.publish(self.CANAL_DASHBOARD, mensaje)
    
    async def publicar_dashboard(self, tipo: str, payload: Dict[str, Any]) -> int:
        """
        Publica mensaje genérico para el dashboard.
        """
        mensaje = json.dumps({
            "tipo": tipo,
            "payload": payload,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        })
        return await self._redis.client.publish(self.CANAL_DASHBOARD, mensaje)
    
    def _determinar_canal(self, evento: DominioEvent) -> str:
        """Determina el canal apropiado según el tipo de evento."""
        if isinstance(evento, PosicionActualizada):
            return self.CANAL_POSICIONES
        elif isinstance(evento, ConflictoDetectado):
            return self.CANAL_ALERTAS
        else:
            return self.CANAL_EVENTOS
    
    # ============================================================
    # SUSCRIPCIÓN
    # ============================================================
    
    def registrar_handler(self, canal: str, handler: Callable[[Dict], Any]) -> None:
        """Registra un handler para un canal específico."""
        if canal not in self._handlers:
            self._handlers[canal] = []
        self._handlers[canal].append(handler)
    
    def remover_handler(self, canal: str, handler: Callable[[Dict], Any]) -> None:
        """Remueve un handler de un canal."""
        if canal in self._handlers and handler in self._handlers[canal]:
            self._handlers[canal].remove(handler)
    
    async def escuchar(self) -> None:
        """
        Inicia la escucha de mensajes en todos los canales.
        Ejecutar en una tarea asíncrona separada.
        """
        if not self._pubsub:
            raise RuntimeError("Pub/Sub no conectado. Llame a connect() primero.")
        
        await self._pubsub.subscribe(*self._handlers.keys())
        self._running = True
        
        async for mensaje in self._pubsub.listen():
            if not self._running:
                break
            
            if mensaje["type"] != "message":
                continue
            
            canal = mensaje["channel"]
            data = json.loads(mensaje["data"])
            
            # Ejecutar handlers registrados
            for handler in self._handlers.get(canal, []):
                try:
                    await handler(data) if __import__('inspect').iscoroutinefunction(handler) else handler(data)
                except Exception as e:
                    print(f"Error en handler de {canal}: {e}")
    
    async def escuchar_canal(self, canal: str) -> None:
        """Escucha un canal específico."""
        if not self._pubsub:
            raise RuntimeError("Pub/Sub no conectado.")
        
        await self._pubsub.subscribe(canal)
        
        async for mensaje in self._pubsub.listen():
            if mensaje["type"] != "message":
                continue
            
            data = json.loads(mensaje["data"])
            for handler in self._handlers.get(canal, []):
                try:
                    await handler(data) if __import__('inspect').iscoroutinefunction(handler) else handler(data)
                except Exception as e:
                    print(f"Error en handler: {e}")
    
    # ============================================================
    # UTILIDADES
    # ============================================================
    
    async def obtener_suscriptores(self, canal: str) -> int:
        """Obtiene el número de suscriptores de un canal."""
        info = await self._redis.client.pubsub_numsub(canal)
        return info[0][1] if info else 0