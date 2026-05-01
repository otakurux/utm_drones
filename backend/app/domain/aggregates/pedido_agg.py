"""pedido_agg.py""" 
from dataclasses import dataclass, field
from typing import List
from uuid import UUID

from ..entities.entrega import Entrega, Paquete
from ..value_objects.direccion import DireccionDestino
from ..events.dominio_event import DominioEvent


@dataclass
class AgregadoPedido:
    """
    Agregado: Pedido
    Raíz: Entrega (Pedido)
    Encapsula Paquete (Entidad), DireccionDestino (Value Object) y ciclo de vida.
    """
    raiz: Entrega = field(default_factory=Entrega)

    @classmethod
    def crear_pedido(
        cls,
        numero_pedido: str,
        cliente_id: UUID,
        tipo: str,
        peso_kg: float,
        origen: DireccionDestino,
        destino: DireccionDestino,
        dimensiones: str = "",
        fragil: bool = False,
    ) -> 'AgregadoPedido':
        """
        Fábrica del agregado Pedido.
        Crea un nuevo pedido completo con todos sus componentes.
        """
        from ..enums.estados import TipoEntrega
        
        paquete = Paquete(
            peso_kg=peso_kg,
            dimensiones_cm=dimensiones,
            fragil=fragil,
        )
        
        entrega = Entrega(
            numero_pedido=numero_pedido,
            cliente_id=cliente_id,
            tipo=TipoEntrega(tipo),
            paquete=paquete,
            direccion_origen=origen,
            direccion_destino=destino,
        )
        
        return cls(raiz=entrega)

    def asignar_a_dron(self, dron_id: UUID, vuelo_id: UUID) -> None:
        """Delega la asignación a la raíz del agregado."""
        self.raiz.asignar_dron(dron_id, vuelo_id)

    def iniciar_ruta(self) -> None:
        """Delega el inicio de ruta a la raíz."""
        self.raiz.iniciar_entrega()

    def confirmar_entrega(self) -> None:
        """Delega la confirmación a la raíz."""
        self.raiz.marcar_entregado()

    def obtener_eventos(self) -> List[DominioEvent]:
        return self.raiz.obtener_eventos_pendientes()

    def to_dict(self) -> dict:
        return self.raiz.to_dict()