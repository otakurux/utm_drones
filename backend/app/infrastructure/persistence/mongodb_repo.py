"""mongodb_repo""" 
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID, uuid4

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, GEOSPHERE

from ...config import config
from ...domain.entities.dron import Dron
from ...domain.entities.vuelo import Vuelo
from ...domain.entities.entrega import Entrega, Paquete
from ...domain.entities.zona_restringida import ZonaRestringida
from ...domain.events.dominio_event import DominioEvent
from ...domain.value_objects.direccion import DireccionDestino
from ...domain.value_objects.plan_vuelo import PlanDeVuelo, Waypoint
from ...domain.value_objects.geocerca import Geocerca
from ...domain.enums.estados import EstadoDron, EstadoVuelo, EstadoEntrega, TipoEntrega, TipoZona


class MongoDBConnection:
    """
    Singleton para la conexión a MongoDB.
    Maneja el cliente y la base de datos de forma centralizada.
    """
    _instance: Optional['MongoDBConnection'] = None
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self) -> None:
        """Establece la conexión con MongoDB."""
        if self._client is None:
            self._client = AsyncIOMotorClient(config.MONGODB_URI)
            self._db = self._client[config.MONGODB_DB]
            await self._crear_indices()
    
    async def disconnect(self) -> None:
        """Cierra la conexión con MongoDB."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
    
    async def _crear_indices(self) -> None:
        """Crea índices necesarios para optimizar consultas."""
        # Índices geoespaciales para drones
        await self._db.drones.create_index([("posicion", GEOSPHERE)])
        await self._db.drones.create_index("numero_serie", unique=True)
        
        # Índices para vuelos
        await self._db.vuelos.create_index("dron_id")
        await self._db.vuelos.create_index("entrega_id")
        await self._db.vuelos.create_index([("estado", ASCENDING), ("fecha_creacion", DESCENDING)])
        
        # Índices para entregas
        await self._db.entregas.create_index("numero_pedido", unique=True)
        await self._db.entregas.create_index([("estado", ASCENDING), ("tipo", ASCENDING)])
        
        # Índices geoespaciales para zonas restringidas
        await self._db.zonas_restringidas.create_index([("coordenadas", GEOSPHERE)])
        
        # Índices para eventos de auditoría
        await self._db.eventos_auditoria.create_index([("timestamp", DESCENDING)])
        await self._db.eventos_auditoria.create_index("aggregate_id")
    
    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._db is None:
            raise RuntimeError("MongoDB no está conectado. Llame a connect() primero.")
        return self._db
    
    @property
    def client(self) -> AsyncIOMotorClient:
        return self._client


class BaseRepository(ABC):
    """Clase base para todos los repositorios MongoDB."""
    
    def __init__(self):
        self._connection = MongoDBConnection()
    
    @property
    def db(self) -> AsyncIOMotorDatabase:
        return self._connection.db
    
    @abstractmethod
    def _to_document(self, entity: Any) -> dict:
        """Convierte una entidad a documento MongoDB."""
        pass
    
    @abstractmethod
    def _from_document(self, document: dict) -> Any:
        """Convierte un documento MongoDB a entidad."""
        pass


class DronRepository(BaseRepository):
    """
    Repositorio para la entidad Dron.
    Colección: drones
    """
    
    @property
    def collection(self):
        return self.db.drones
    
    def _to_document(self, dron: Dron) -> dict:
        return {
            "_id": str(dron.id),
            "id": str(dron.id),
            "numero_serie": dron.numero_serie,
            "modelo": dron.modelo,
            "capacidad_carga_kg": dron.capacidad_carga_kg,
            "bateria_maxima_mah": dron.bateria_maxima_mah,
            "bateria_porcentaje": dron.bateria_porcentaje,
            "estado": dron.estado.value,
            "posicion": {
                "type": "Point",
                "coordinates": [dron.longitud, dron.latitud, dron.altitud],
            },
            "fecha_registro": dron.fecha_registro,
            "ultima_actualizacion": dron.ultima_actualizacion,
            "total_vuelos": dron.total_vuelos,
            "horas_vuelo_acumuladas": dron.horas_vuelo_acumuladas,
        }
    
    def _from_document(self, doc: dict) -> Dron:
        coords = doc.get("posicion", {}).get("coordinates", [0, 0, 0])
        return Dron(
            id=UUID(doc["id"]),
            numero_serie=doc["numero_serie"],
            modelo=doc.get("modelo", ""),
            capacidad_carga_kg=doc.get("capacidad_carga_kg", 0.0),
            bateria_maxima_mah=doc.get("bateria_maxima_mah", 0),
            bateria_porcentaje=doc.get("bateria_porcentaje", 100.0),
            estado=EstadoDron(doc.get("estado", "disponible")),
            latitud=coords[1] if len(coords) > 1 else 0.0,
            longitud=coords[0] if len(coords) > 0 else 0.0,
            altitud=coords[2] if len(coords) > 2 else 0.0,
            fecha_registro=doc.get("fecha_registro", datetime.utcnow()),
            ultima_actualizacion=doc.get("ultima_actualizacion", datetime.utcnow()),
            total_vuelos=doc.get("total_vuelos", 0),
            horas_vuelo_acumuladas=doc.get("horas_vuelo_acumuladas", 0.0),
        )
    
    async def guardar(self, dron: Dron) -> None:
        """Guarda o actualiza un dron."""
        document = self._to_document(dron)
        await self.collection.replace_one(
            {"_id": str(dron.id)},
            document,
            upsert=True,
        )
    
    async def obtener_por_id(self, dron_id: UUID) -> Optional[Dron]:
        """Obtiene un dron por su ID."""
        doc = await self.collection.find_one({"_id": str(dron_id)})
        return self._from_document(doc) if doc else None
    
    async def obtener_por_serie(self, numero_serie: str) -> Optional[Dron]:
        """Obtiene un dron por su número de serie."""
        doc = await self.collection.find_one({"numero_serie": numero_serie})
        return self._from_document(doc) if doc else None
    
    async def listar_todos(self, skip: int = 0, limit: int = 100) -> List[Dron]:
        """Lista todos los drones con paginación."""
        cursor = self.collection.find().skip(skip).limit(limit)
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_por_estado(self, estado: EstadoDron) -> List[Dron]:
        """Lista drones filtrados por estado."""
        cursor = self.collection.find({"estado": estado.value})
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_disponibles(self) -> List[Dron]:
        """Lista drones disponibles para asignación."""
        cursor = self.collection.find({
            "estado": EstadoDron.DISPONIBLE.value,
            "bateria_porcentaje": {"$gte": 20.0},
        })
        return [self._from_document(doc) async for doc in cursor]
    
    async def actualizar_posicion(
        self,
        dron_id: UUID,
        lat: float,
        lng: float,
        alt: float,
        bateria: float,
    ) -> None:
        """Actualiza solo la posición y batería (operación frecuente)."""
        await self.collection.update_one(
            {"_id": str(dron_id)},
            {
                "$set": {
                    "posicion": {
                        "type": "Point",
                        "coordinates": [lng, lat, alt],
                    },
                    "bateria_porcentaje": bateria,
                    "ultima_actualizacion": datetime.utcnow(),
                }
            }
        )
    
    async def actualizar_estado(self, dron_id: UUID, estado: EstadoDron) -> None:
        """Actualiza el estado de un dron."""
        await self.collection.update_one(
            {"_id": str(dron_id)},
            {
                "$set": {
                    "estado": estado.value,
                    "ultima_actualizacion": datetime.utcnow(),
                }
            }
        )
    
    async def eliminar(self, dron_id: UUID) -> bool:
        """Elimina un dron permanentemente."""
        result = await self.collection.delete_one({"_id": str(dron_id)})
        return result.deleted_count > 0
    
    async def buscar_cercanos(
        self,
        lat: float,
        lng: float,
        radio_metros: float = 1000,
    ) -> List[Dron]:
        """Busca drones cercanos a un punto geográfico."""
        cursor = self.collection.find({
            "posicion": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [lng, lat],
                    },
                    "$maxDistance": radio_metros,
                }
            }
        })
        return [self._from_document(doc) async for doc in cursor]


class VueloRepository(BaseRepository):
    """
    Repositorio para la entidad Vuelo.
    Colección: vuelos
    """
    
    @property
    def collection(self):
        return self.db.vuelos
    
    def _to_document(self, vuelo: Vuelo) -> dict:
        return {
            "_id": str(vuelo.id),
            "id": str(vuelo.id),
            "dron_id": str(vuelo.dron_id) if vuelo.dron_id else None,
            "entrega_id": str(vuelo.entrega_id) if vuelo.entrega_id else None,
            "estado": vuelo.estado.value,
            "plan_vuelo": vuelo.plan_vuelo.to_dict() if vuelo.plan_vuelo else None,
            "fecha_creacion": vuelo.fecha_creacion,
            "fecha_despegue": vuelo.fecha_despegue,
            "fecha_completado": vuelo.fecha_completado,
            "waypoint_actual": vuelo.waypoint_actual,
            "distancia_recorrida": vuelo.distancia_recorrida,
        }
    
    def _from_document(self, doc: dict) -> Vuelo:
        plan_dict = doc.get("plan_vuelo")
        plan = None
        if plan_dict:
            plan = PlanDeVuelo(
                id=UUID(plan_dict.get("id", str(uuid4()))),
                altitud_minima=plan_dict.get("altitud_minima", 30.0),
                altitud_maxima=plan_dict.get("altitud_maxima", 120.0),
                velocidad_maxima=plan_dict.get("velocidad_maxima", 15.0),
            )
            for wp_data in plan_dict.get("waypoints", []):
                wp = Waypoint(
                    orden=wp_data.get("orden", 0),
                    latitud=wp_data.get("lat", 0.0),
                    longitud=wp_data.get("lng", 0.0),
                    altitud=wp_data.get("alt", 0.0),
                    velocidad_max=wp_data.get("velocidad_max", 15.0),
                )
                plan.waypoints.append(wp)
            plan._recalcular_metricas()
        
        return Vuelo(
            id=UUID(doc["id"]),
            dron_id=UUID(doc["dron_id"]) if doc.get("dron_id") else None,
            entrega_id=UUID(doc["entrega_id"]) if doc.get("entrega_id") else None,
            estado=EstadoVuelo(doc.get("estado", "planificado")),
            plan_vuelo=plan or PlanDeVuelo(),
            fecha_creacion=doc.get("fecha_creacion", datetime.utcnow()),
            fecha_despegue=doc.get("fecha_despegue"),
            fecha_completado=doc.get("fecha_completado"),
            waypoint_actual=doc.get("waypoint_actual", 0),
            distancia_recorrida=doc.get("distancia_recorrida", 0.0),
        )
    
    async def guardar(self, vuelo: Vuelo) -> None:
        """Guarda o actualiza un vuelo."""
        document = self._to_document(vuelo)
        await self.collection.replace_one(
            {"_id": str(vuelo.id)},
            document,
            upsert=True,
        )
    
    async def obtener_por_id(self, vuelo_id: UUID) -> Optional[Vuelo]:
        """Obtiene un vuelo por su ID."""
        doc = await self.collection.find_one({"_id": str(vuelo_id)})
        return self._from_document(doc) if doc else None
    
    async def listar_activos(self) -> List[Vuelo]:
        """Lista vuelos activos (EN_RUTA)."""
        cursor = self.collection.find({"estado": EstadoVuelo.EN_RUTA.value})
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_por_dron(self, dron_id: UUID) -> List[Vuelo]:
        """Lista vuelos de un dron específico."""
        cursor = self.collection.find({"dron_id": str(dron_id)}).sort("fecha_creacion", DESCENDING)
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_por_entrega(self, entrega_id: UUID) -> Optional[Vuelo]:
        """Obtiene el vuelo asociado a una entrega."""
        doc = await self.collection.find_one({"entrega_id": str(entrega_id)})
        return self._from_document(doc) if doc else None
    
    async def actualizar_estado(self, vuelo_id: UUID, estado: EstadoVuelo) -> None:
        """Actualiza el estado de un vuelo."""
        update = {
            "estado": estado.value,
        }
        if estado == EstadoVuelo.EN_RUTA:
            update["fecha_despegue"] = datetime.utcnow()
        elif estado in [EstadoVuelo.COMPLETADO, EstadoVuelo.CANCELADO, EstadoVuelo.EMERGENCIA]:
            update["fecha_completado"] = datetime.utcnow()
        
        await self.collection.update_one(
            {"_id": str(vuelo_id)},
            {"$set": update}
        )
    
    async def actualizar_waypoint(self, vuelo_id: UUID, waypoint_index: int) -> None:
        """Actualiza el waypoint actual del vuelo."""
        await self.collection.update_one(
            {"_id": str(vuelo_id)},
            {"$set": {"waypoint_actual": waypoint_index}}
        )


class EntregaRepository(BaseRepository):
    """
    Repositorio para la entidad Entrega.
    Colección: entregas
    """
    
    @property
    def collection(self):
        return self.db.entregas
    
    def _to_document(self, entrega: Entrega) -> dict:
        return {
            "_id": str(entrega.id),
            "id": str(entrega.id),
            "numero_pedido": entrega.numero_pedido,
            "cliente_id": str(entrega.cliente_id) if entrega.cliente_id else None,
            "tipo": entrega.tipo.value,
            "prioridad": entrega.prioridad,
            "paquete": {
                "id": str(entrega.paquete.id),
                "peso_kg": entrega.paquete.peso_kg,
                "dimensiones_cm": entrega.paquete.dimensiones_cm,
                "fragil": entrega.paquete.fragil,
                "requiere_refrigeracion": entrega.paquete.requiere_refrigeracion,
                "descripcion": entrega.paquete.descripcion,
            },
            "direccion_origen": entrega.direccion_origen.to_dict(),
            "direccion_destino": entrega.direccion_destino.to_dict(),
            "estado": entrega.estado.value,
            "dron_asignado_id": str(entrega.dron_asignado_id) if entrega.dron_asignado_id else None,
            "vuelo_asignado_id": str(entrega.vuelo_asignado_id) if entrega.vuelo_asignado_id else None,
            "fecha_creacion": entrega.fecha_creacion,
            "fecha_asignacion": entrega.fecha_asignacion,
            "fecha_inicio_ruta": entrega.fecha_inicio_ruta,
            "fecha_entrega": entrega.fecha_entrega,
        }
    
    def _from_document(self, doc: dict) -> Entrega:
        paquete_data = doc.get("paquete", {})
        paquete = Paquete(
            id=UUID(paquete_data.get("id", str(uuid4()))),
            peso_kg=paquete_data.get("peso_kg", 0.0),
            dimensiones_cm=paquete_data.get("dimensiones_cm", ""),
            fragil=paquete_data.get("fragil", False),
            requiere_refrigeracion=paquete_data.get("requiere_refrigeracion", False),
            descripcion=paquete_data.get("descripcion", ""),
        )
        
        origen_data = doc.get("direccion_origen", {})
        destino_data = doc.get("direccion_destino", {})
        
        return Entrega(
            id=UUID(doc["id"]),
            numero_pedido=doc["numero_pedido"],
            cliente_id=UUID(doc["cliente_id"]) if doc.get("cliente_id") else None,
            tipo=TipoEntrega(doc.get("tipo", "general")),
            paquete=paquete,
            direccion_origen=DireccionDestino(
                latitud=origen_data.get("latitud", 0.0),
                longitud=origen_data.get("longitud", 0.0),
                altitud=origen_data.get("altitud", 0.0),
                instrucciones=origen_data.get("instrucciones", ""),
            ),
            direccion_destino=DireccionDestino(
                latitud=destino_data.get("latitud", 0.0),
                longitud=destino_data.get("longitud", 0.0),
                altitud=destino_data.get("altitud", 0.0),
                instrucciones=destino_data.get("instrucciones", ""),
            ),
            estado=EstadoEntrega(doc.get("estado", "pendiente")),
            dron_asignado_id=UUID(doc["dron_asignado_id"]) if doc.get("dron_asignado_id") else None,
            vuelo_asignado_id=UUID(doc["vuelo_asignado_id"]) if doc.get("vuelo_asignado_id") else None,
            fecha_creacion=doc.get("fecha_creacion", datetime.utcnow()),
            fecha_asignacion=doc.get("fecha_asignacion"),
            fecha_inicio_ruta=doc.get("fecha_inicio_ruta"),
            fecha_entrega=doc.get("fecha_entrega"),
        )
    
    async def guardar(self, entrega: Entrega) -> None:
        """Guarda o actualiza una entrega."""
        document = self._to_document(entrega)
        await self.collection.replace_one(
            {"_id": str(entrega.id)},
            document,
            upsert=True,
        )
    
    async def obtener_por_id(self, entrega_id: UUID) -> Optional[Entrega]:
        """Obtiene una entrega por su ID."""
        doc = await self.collection.find_one({"_id": str(entrega_id)})
        return self._from_document(doc) if doc else None
    
    async def obtener_por_pedido(self, numero_pedido: str) -> Optional[Entrega]:
        """Obtiene una entrega por su número de pedido."""
        doc = await self.collection.find_one({"numero_pedido": numero_pedido})
        return self._from_document(doc) if doc else None
    
    async def listar_por_estado(self, estado: EstadoEntrega) -> List[Entrega]:
        """Lista entregas filtradas por estado."""
        cursor = self.collection.find({"estado": estado.value})
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_pendientes(self) -> List[Entrega]:
        """Lista entregas pendientes ordenadas por prioridad."""
        cursor = self.collection.find(
            {"estado": EstadoEntrega.PENDIENTE.value}
        ).sort([("prioridad", DESCENDING), ("fecha_creacion", ASCENDING)])
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_criticas(self) -> List[Entrega]:
        """Lista entregas críticas (medicina) pendientes o en ruta."""
        cursor = self.collection.find({
            "tipo": TipoEntrega.MEDICINA.value,
            "estado": {"$in": [EstadoEntrega.PENDIENTE.value, EstadoEntrega.EN_RUTA.value]},
        })
        return [self._from_document(doc) async for doc in cursor]
    
    async def actualizar_estado(self, entrega_id: UUID, estado: EstadoEntrega) -> None:
        """Actualiza el estado de una entrega."""
        update = {"estado": estado.value}
        if estado == EstadoEntrega.ASIGNADA:
            update["fecha_asignacion"] = datetime.utcnow()
        elif estado == EstadoEntrega.EN_RUTA:
            update["fecha_inicio_ruta"] = datetime.utcnow()
        elif estado in [EstadoEntrega.ENTREGADO, EstadoEntrega.FALLIDO]:
            update["fecha_entrega"] = datetime.utcnow()
        
        await self.collection.update_one(
            {"_id": str(entrega_id)},
            {"$set": update}
        )
    
    async def asignar_dron_vuelo(
        self,
        entrega_id: UUID,
        dron_id: UUID,
        vuelo_id: UUID,
    ) -> None:
        """Asigna dron y vuelo a una entrega."""
        await self.collection.update_one(
            {"_id": str(entrega_id)},
            {
                "$set": {
                    "dron_asignado_id": str(dron_id),
                    "vuelo_asignado_id": str(vuelo_id),
                    "estado": EstadoEntrega.ASIGNADA.value,
                    "fecha_asignacion": datetime.utcnow(),
                }
            }
        )


class ZonaRepository(BaseRepository):
    """
    Repositorio para la entidad ZonaRestringida.
    Colección: zonas_restringidas
    """
    
    @property
    def collection(self):
        return self.db.zonas_restringidas
    
    def _to_document(self, zona: ZonaRestringida) -> dict:
        # Convertir coordenadas a formato GeoJSON Polygon
        coords = zona.coordenadas
        if coords and coords[0] != coords[-1]:
            coords = coords + [coords[0]]  # Cerrar polígono
        
        return {
            "_id": str(zona.id),
            "id": str(zona.id),
            "codigo": zona.codigo,
            "nombre": zona.nombre,
            "descripcion": zona.descripcion,
            "geometria": {
                "type": "Polygon",
                "coordinates": [[
                    [c[1], c[0]] for c in coords  # [lng, lat] para GeoJSON
                ]] if coords else [],
            },
            "coordenadas": zona.coordenadas,  # Guardar también en formato original
            "altitud_min": zona.altitud_min,
            "altitud_max": zona.altitud_max,
            "tipo": zona.tipo.value,
            "vigencia_desde": zona.vigencia_desde,
            "vigencia_hasta": zona.vigencia_hasta,
            "autoridad_emisora": zona.autoridad_emisora,
            "fecha_creacion": zona.fecha_creacion,
            "activa": zona.activa,
        }
    
    def _from_document(self, doc: dict) -> ZonaRestringida:
        return ZonaRestringida(
            id=UUID(doc["id"]),
            codigo=doc.get("codigo", ""),
            nombre=doc.get("nombre", ""),
            descripcion=doc.get("descripcion", ""),
            coordenadas=[(c[0], c[1]) for c in doc.get("coordenadas", [])],
            altitud_min=doc.get("altitud_min", 0.0),
            altitud_max=doc.get("altitud_max", 500.0),
            tipo=TipoZona(doc.get("tipo", "permanente")),
            vigencia_desde=doc.get("vigencia_desde", datetime.utcnow()),
            vigencia_hasta=doc.get("vigencia_hasta"),
            autoridad_emisora=doc.get("autoridad_emisora", ""),
            fecha_creacion=doc.get("fecha_creacion", datetime.utcnow()),
            activa=doc.get("activa", True),
        )
    
    async def guardar(self, zona: ZonaRestringida) -> None:
        """Guarda o actualiza una zona restringida."""
        document = self._to_document(zona)
        await self.collection.replace_one(
            {"_id": str(zona.id)},
            document,
            upsert=True,
        )
    
    async def obtener_por_id(self, zona_id: UUID) -> Optional[ZonaRestringida]:
        """Obtiene una zona por su ID."""
        doc = await self.collection.find_one({"_id": str(zona_id)})
        return self._from_document(doc) if doc else None
    
    async def obtener_por_codigo(self, codigo: str) -> Optional[ZonaRestringida]:
        """Obtiene una zona por su código."""
        doc = await self.collection.find_one({"codigo": codigo})
        return self._from_document(doc) if doc else None
    
    async def listar_activas(self) -> List[ZonaRestringida]:
        """Lista zonas activas y vigentes."""
        ahora = datetime.utcnow()
        cursor = self.collection.find({
            "activa": True,
            "$or": [
                {"tipo": "permanente"},
                {
                    "tipo": "temporal",
                    "vigencia_desde": {"$lte": ahora},
                    "vigencia_hasta": {"$gte": ahora},
                }
            ]
        })
        return [self._from_document(doc) async for doc in cursor]
    
    async def listar_todas(self, skip: int = 0, limit: int = 100) -> List[ZonaRestringida]:
        """Lista todas las zonas con paginación."""
        cursor = self.collection.find().skip(skip).limit(limit)
        return [self._from_document(doc) async for doc in cursor]
    
    async def desactivar(self, zona_id: UUID) -> None:
        """Desactiva una zona restringida."""
        await self.collection.update_one(
            {"_id": str(zona_id)},
            {"$set": {"activa": False}}
        )
    
    async def buscar_en_area(
        self,
        lat: float,
        lng: float,
        radio_metros: float = 1000,
    ) -> List[ZonaRestringida]:
        """Busca zonas que intersectan un área circular."""
        cursor = self.collection.find({
            "geometria": {
                "$geoIntersects": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [lng, lat],
                    }
                }
            }
        })
        return [self._from_document(doc) async for doc in cursor]


class EventoAuditoriaRepository(BaseRepository):
    """
    Repositorio para eventos de dominio (auditoría).
    Colección: eventos_auditoria
    """
    
    @property
    def collection(self):
        return self.db.eventos_auditoria
    
    async def guardar_evento(self, evento: DominioEvent) -> None:
        """Persiste un evento de dominio para auditoría."""
        document = {
            "_id": str(uuid4()),
            "event_id": str(evento.event_id),
            "timestamp": evento.timestamp,
            "tipo": evento.__class__.__name__,
            "aggregate_id": str(evento.aggregate_id) if evento.aggregate_id else None,
            "payload": evento.to_dict(),
        }
        await self.collection.insert_one(document)
    
    async def listar_por_aggregate(
        self,
        aggregate_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[dict]:
        """Lista eventos de un aggregate específico."""
        cursor = self.collection.find(
            {"aggregate_id": str(aggregate_id)}
        ).sort("timestamp", DESCENDING).skip(skip).limit(limit)
        return [doc async for doc in cursor]
    
    async def listar_por_tipo(
        self,
        tipo_evento: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[dict]:
        """Lista eventos por tipo."""
        cursor = self.collection.find(
            {"tipo": tipo_evento}
        ).sort("timestamp", DESCENDING).skip(skip).limit(limit)
        return [doc async for doc in cursor]
    
    async def listar_recientes(self, minutos: int = 60) -> List[dict]:
        """Lista eventos recientes."""
        desde = datetime.utcnow() - __import__('datetime').timedelta(minutes=minutos)
        cursor = self.collection.find(
            {"timestamp": {"$gte": desde}}
        ).sort("timestamp", DESCENDING)
        return [doc async for doc in cursor]