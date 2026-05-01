"""websocket_manager""" 
import json
from typing import Dict, List, Optional, Set
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from ...config import config


class WebSocketManager:
    """
    Gestor de conexiones WebSocket para el dashboard en tiempo real.
    Maneja múltiples clientes y reenvía eventos del sistema.
    
    Funcionalidades:
    - Múltiples clientes simultáneos
    - Suscripción a canales específicos
    - Heartbeat automático
    - Broadcast eficiente
    """
    
    def __init__(self):
        # Conexiones activas: {websocket: {canales: Set[str], cliente_id: str}}
        self._conexiones: Dict[WebSocket, Dict[str, any]] = {}
        # Índice por canal: {canal: Set[WebSocket]}
        self._canales: Dict[str, Set[WebSocket]] = {
            "posiciones": set(),
            "alertas": set(),
            "eventos": set(),
            "estadisticas": set(),
            "all": set(),
        }
    
    # ============================================================
    # GESTIÓN DE CONEXIONES
    # ============================================================
    
    async def conectar(self, websocket: WebSocket, cliente_id: Optional[str] = None) -> None:
        """Acepta una nueva conexión WebSocket."""
        await websocket.accept()
        
        self._conexiones[websocket] = {
            "canales": {"all"},  # Por defecto suscrito a todo
            "cliente_id": cliente_id or str(id(websocket)),
            "conectado_en": __import__('datetime').datetime.utcnow().isoformat(),
        }
        
        self._canales["all"].add(websocket)
        
        # Enviar mensaje de bienvenida
        await self._enviar_a_cliente(websocket, {
            "tipo": "conexion_establecida",
            "payload": {
                "cliente_id": self._conexiones[websocket]["cliente_id"],
                "canales_disponibles": list(self._canales.keys()),
                "heartbeat_interval": config.WS_HEARTBEAT_INTERVAL,
            }
        })
    
    async def desconectar(self, websocket: WebSocket) -> None:
        """Cierra una conexión WebSocket y limpia recursos."""
        if websocket not in self._conexiones:
            return
        
        # Remover de todos los canales
        info = self._conexiones[websocket]
        for canal in info["canales"]:
            if canal in self._canales:
                self._canales[canal].discard(websocket)
        
        del self._conexiones[websocket]
    
    async def suscribir(self, websocket: WebSocket, canales: List[str]) -> None:
        """Suscribe un cliente a canales específicos."""
        if websocket not in self._conexiones:
            return
        
        # Remover de canales actuales (excepto 'all')
        for canal in list(self._conexiones[websocket]["canales"]):
            if canal != "all":
                self._canales[canal].discard(websocket)
                self._conexiones[websocket]["canales"].discard(canal)
        
        # Agregar nuevos canales
        for canal in canales:
            if canal in self._canales:
                self._canales[canal].add(websocket)
                self._conexiones[websocket]["canales"].add(canal)
        
        await self._enviar_a_cliente(websocket, {
            "tipo": "suscripcion_actualizada",
            "payload": {
                "canales_activos": list(self._conexiones[websocket]["canales"]),
            }
        })
    
    # ============================================================
    # ENVÍO DE MENSAJES
    # ============================================================
    
    async def _enviar_a_cliente(self, websocket: WebSocket, mensaje: Dict) -> None:
        """Envía un mensaje a un cliente específico."""
        try:
            await websocket.send_json(mensaje)
        except Exception:
            # Si falla, marcar para desconexión
            await self.desconectar(websocket)
    
    async def enviar_a_cliente(
        self,
        cliente_id: str,
        mensaje: Dict,
    ) -> bool:
        """Envía un mensaje a un cliente específico por ID."""
        for websocket, info in self._conexiones.items():
            if info["cliente_id"] == cliente_id:
                await self._enviar_a_cliente(websocket, mensaje)
                return True
        return False
    
    async def broadcast(self, mensaje: Dict, canal: Optional[str] = None) -> int:
        """
        Envía un mensaje a todos los clientes suscritos.
        Si canal es None, envía a todos.
        """
        if canal and canal in self._canales:
            clientes = self._canales[canal].copy()
        else:
            clientes = set(self._conexiones.keys())
        
        enviados = 0
        desconectar = []
        
        for websocket in clientes:
            try:
                await websocket.send_json(mensaje)
                enviados += 1
            except Exception:
                desconectar.append(websocket)
        
        # Limpiar conexiones caídas
        for ws in desconectar:
            await self.desconectar(ws)
        
        return enviados
    
    async def broadcast_posicion(self, data: Dict) -> int:
        """Broadcast optimizado para actualizaciones de posición."""
        return await self.broadcast({
            "tipo": "PosicionActualizada",
            "payload": data,
        }, canal="posiciones")
    
    async def broadcast_alerta(self, data: Dict) -> int:
        """Broadcast para alertas críticas."""
        return await self.broadcast({
            "tipo": "Alerta",
            "payload": data,
        }, canal="alertas")
    
    async def broadcast_evento(self, tipo: str, payload: Dict) -> int:
        """Broadcast genérico para eventos de dominio."""
        return await self.broadcast({
            "tipo": tipo,
            "payload": payload,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        }, canal="eventos")
    
    async def enviar_estadisticas(self, estadisticas: Dict) -> int:
        """Envía estadísticas actualizadas a los clientes interesados."""
        return await self.broadcast({
            "tipo": "Estadisticas",
            "payload": estadisticas,
        }, canal="estadisticas")
    
    # ============================================================
    # HEARTBEAT
    # ============================================================
    
    async def enviar_heartbeat(self) -> int:
        """Envía heartbeat a todos los clientes conectados."""
        return await self.broadcast({
            "tipo": "heartbeat",
            "payload": {
                "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
                "clientes_conectados": len(self._conexiones),
            }
        })
    
    # ============================================================
    # MÉTRICAS
    # ============================================================
    
    def obtener_estadisticas_conexiones(self) -> Dict:
        """Retorna estadísticas de conexiones activas."""
        return {
            "total_conexiones": len(self._conexiones),
            "conexiones_por_canal": {
                canal: len(clientes) for canal, clientes in self._canales.items()
            },
            "clientes": [
                {
                    "cliente_id": info["cliente_id"],
                    "canales": list(info["canales"]),
                    "conectado_desde": info["conectado_en"],
                }
                for info in self._conexiones.values()
            ]
        }
    
    async def manejar_mensaje_cliente(self, websocket: WebSocket, data: str) -> None:
        """
        Maneja mensajes recibidos de los clientes.
        Protocolo: {"accion": "suscribir", "canales": ["posiciones", "alertas"]}
        """
        try:
            mensaje = json.loads(data)
            accion = mensaje.get("accion")
            
            if accion == "suscribir":
                canales = mensaje.get("canales", ["all"])
                await self.suscribir(websocket, canales)
            
            elif accion == "ping":
                await self._enviar_a_cliente(websocket, {
                    "tipo": "pong",
                    "payload": {"timestamp": __import__('datetime').datetime.utcnow().isoformat()}
                })
            
            elif accion == "estadisticas":
                await self._enviar_a_cliente(websocket, {
                    "tipo": "estadisticas_conexiones",
                    "payload": self.obtener_estadisticas_conexiones(),
                })
            
            else:
                await self._enviar_a_cliente(websocket, {
                    "tipo": "error",
                    "payload": {"mensaje": f"Acción desconocida: {accion}"}
                })
                
        except json.JSONDecodeError:
            await self._enviar_a_cliente(websocket, {
                "tipo": "error",
                "payload": {"mensaje": "JSON inválido"}
            })