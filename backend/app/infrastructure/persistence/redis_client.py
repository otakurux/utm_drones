"""redis_client""" 
import json
from typing import Optional, List, Dict, Any, Union
from uuid import UUID

import redis.asyncio as redis

from ...config import config


class RedisClient:
    """
    Cliente Redis para operaciones en tiempo real.
    Maneja posiciones, estados, colas y estructuras de datos.
    """
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """Establece conexión con Redis."""
        self._client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD or None,
            decode_responses=True,
        )
    
    async def disconnect(self) -> None:
        """Cierra conexión con Redis."""
        if self._client:
            await self._client.close()
            self._client = None
    
    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis no está conectado. Llame a connect() primero.")
        return self._client
    
    # ============================================================
    # POSICIONES DE DRONES (Hashes)
    # ============================================================
    
    def _key_posicion(self, dron_id: Union[UUID, str]) -> str:
        return f"drone:{str(dron_id)}:pos"
    
    def _key_estado(self, dron_id: Union[UUID, str]) -> str:
        return f"drone:{str(dron_id)}:estado"
    
    async def actualizar_posicion(
        self,
        dron_id: Union[UUID, str],
        lat: float,
        lng: float,
        alt: float,
        velocidad: float = 0.0,
        bateria: float = 100.0,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Actualiza la posición de un dron en Redis Hash.
        Se invoca cada 500ms.
        """
        data = {
            "lat": str(lat),
            "lng": str(lng),
            "alt": str(alt),
            "velocidad": str(velocidad),
            "bateria": str(bateria),
            "timestamp": timestamp or __import__('datetime').datetime.utcnow().isoformat(),
        }
        await self.client.hset(self._key_posicion(dron_id), mapping=data)
        # Expirar después de 5 minutos de inactividad
        await self.client.expire(self._key_posicion(dron_id), 300)
    
    async def obtener_posicion(self, dron_id: Union[UUID, str]) -> Optional[Dict[str, Any]]:
        """Obtiene la última posición conocida de un dron."""
        data = await self.client.hgetall(self._key_posicion(dron_id))
        if not data:
            return None
        
        return {
            "dron_id": str(dron_id),
            "lat": float(data.get("lat", 0)),
            "lng": float(data.get("lng", 0)),
            "alt": float(data.get("alt", 0)),
            "velocidad": float(data.get("velocidad", 0)),
            "bateria": float(data.get("bateria", 100)),
            "timestamp": data.get("timestamp"),
        }
    
    async def obtener_posiciones_todas(self) -> List[Dict[str, Any]]:
        """Obtiene posiciones de todos los drones activos."""
        keys = await self.client.keys("drone:*:pos")
        posiciones = []
        for key in keys:
            dron_id = key.split(":")[1]
            pos = await self.obtener_posicion(dron_id)
            if pos:
                posiciones.append(pos)
        return posiciones
    
    # ============================================================
    # ESTADOS DE DRONES
    # ============================================================
    
    async def actualizar_estado(
        self,
        dron_id: Union[UUID, str],
        estado: str,
    ) -> None:
        """Actualiza el estado operativo de un dron."""
        await self.client.set(self._key_estado(dron_id), estado, ex=3600)
    
    async def obtener_estado(self, dron_id: Union[UUID, str]) -> Optional[str]:
        """Obtiene el estado actual de un dron."""
        return await self.client.get(self._key_estado(dron_id))
    
    # ============================================================
    # TRÁFICO ACTIVO (Set)
    # ============================================================
    
    KEY_TRAFICO_ACTIVO = "trafico:activo"
    
    async def registrar_vuelo_activo(self, vuelo_id: Union[UUID, str]) -> None:
        """Registra un vuelo como activo."""
        await self.client.sadd(self.KEY_TRAFICO_ACTIVO, str(vuelo_id))
    
    async def remover_vuelo_activo(self, vuelo_id: Union[UUID, str]) -> None:
        """Remueve un vuelo del tráfico activo."""
        await self.client.srem(self.KEY_TRAFICO_ACTIVO, str(vuelo_id))
    
    async def obtener_vuelos_activos(self) -> List[str]:
        """Obtiene IDs de vuelos activos."""
        return list(await self.client.smembers(self.KEY_TRAFICO_ACTIVO))
    
    # ============================================================
    # COLA DE PRIORIDAD DE ENTREGAS (Sorted Set)
    # ============================================================
    
    KEY_COLA_ENTREGAS = "cola:entregas"
    
    async def encolar_entrega(
        self,
        entrega_id: Union[UUID, str],
        score: float,
    ) -> None:
        """Agrega una entrega a la cola de prioridad."""
        await self.client.zadd(self.KEY_COLA_ENTREGAS, {str(entrega_id): score})
    
    async def desencolar_entrega(self) -> Optional[str]:
        """
        Obtiene y remueve la entrega con mayor prioridad (mayor score).
        """
        # zpopmax retorna el elemento con score más alto
        resultado = await self.client.zpopmax(self.KEY_COLA_ENTREGAS)
        if resultado:
            return resultado[0][0]  # (member, score)
        return None
    
    async def obtener_cola_entregas(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene la cola ordenada por prioridad."""
        items = await self.client.zrevrange(
            self.KEY_COLA_ENTREGAS, 0, limit - 1, withscores=True
        )
        return [
            {"entrega_id": item[0], "score": item[1]}
            for item in items
        ]
    
    async def remover_de_cola(self, entrega_id: Union[UUID, str]) -> None:
        """Remueve una entrega específica de la cola."""
        await self.client.zrem(self.KEY_COLA_ENTREGAS, str(entrega_id))
    
    async def actualizar_score(
        self,
        entrega_id: Union[UUID, str],
        nuevo_score: float,
    ) -> None:
        """Actualiza el score de una entrega en la cola."""
        await self.client.zadd(self.KEY_COLA_ENTREGAS, {str(entrega_id): nuevo_score})
    
    # ============================================================
    # RUTAS ACTIVAS (Hash por vuelo)
    # ============================================================
    
    def _key_ruta(self, vuelo_id: Union[UUID, str]) -> str:
        return f"ruta:{str(vuelo_id)}"
    
    async def guardar_ruta_activa(
        self,
        vuelo_id: Union[UUID, str],
        waypoints: List[Dict[str, Any]],
        prioridad: int = 1,
    ) -> None:
        """Guarda la ruta de un vuelo activo para detección de conflictos."""
        data = {
            "waypoints": json.dumps(waypoints),
            "prioridad": str(prioridad),
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        }
        await self.client.hset(self._key_ruta(vuelo_id), mapping=data)
        await self.client.expire(self._key_ruta(vuelo_id), 7200)  # 2 horas
    
    async def obtener_ruta_activa(
        self,
        vuelo_id: Union[UUID, str],
    ) -> Optional[Dict[str, Any]]:
        """Obtiene la ruta activa de un vuelo."""
        data = await self.client.hgetall(self._key_ruta(vuelo_id))
        if not data:
            return None
        
        return {
            "vuelo_id": str(vuelo_id),
            "waypoints": json.loads(data.get("waypoints", "[]")),
            "prioridad": int(data.get("prioridad", 1)),
            "timestamp": data.get("timestamp"),
        }
    
    async def obtener_todas_rutas_activas(self) -> List[Dict[str, Any]]:
        """Obtiene todas las rutas activas."""
        keys = await self.client.keys("ruta:*")
        rutas = []
        for key in keys:
            vuelo_id = key.split(":")[1]
            ruta = await self.obtener_ruta_activa(vuelo_id)
            if ruta:
                rutas.append(ruta)
        return rutas
    
    async def eliminar_ruta(self, vuelo_id: Union[UUID, str]) -> None:
        """Elimina una ruta activa."""
        await self.client.delete(self._key_ruta(vuelo_id))
    
    # ============================================================
    # MÉTRICAS Y ESTADÍSTICAS
    # ============================================================
    
    async def incrementar_contador(self, key: str, cantidad: int = 1) -> int:
        """Incrementa un contador genérico."""
        return await self.client.incrby(key, cantidad)
    
    async def obtener_contador(self, key: str) -> int:
        """Obtiene el valor de un contador."""
        valor = await self.client.get(key)
        return int(valor) if valor else 0
    
    async def guardar_metrica(
        self,
        key: str,
        valor: Union[str, int, float],
        expiracion_seg: int = 3600,
    ) -> None:
        """Guarda una métrica con expiración."""
        await self.client.setex(key, expiracion_seg, str(valor))
    
    async def obtener_metrica(self, key: str) -> Optional[str]:
        """Obtiene una métrica."""
        return await self.client.get(key)
    
    # ============================================================
    # LIMPIEZA
    # ============================================================
    
    async def limpiar_datos_dron(self, dron_id: Union[UUID, str]) -> None:
        """Limpia todos los datos de un dron de Redis."""
        keys = await self.client.keys(f"drone:{str(dron_id)}:*")
        if keys:
            await self.client.delete(*keys)
    
    async def limpiar_todo(self) -> None:
        """Limpia todas las claves de la base de datos actual."""
        await self.client.flushdb()