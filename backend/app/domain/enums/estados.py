from enum import Enum, auto


class EstadoDron(str, Enum):
    """Estados posibles de un dron en la flota."""
    DISPONIBLE = "disponible"
    EN_VUELO = "en_vuelo"
    CARGANDO = "cargando"
    MANTENIMIENTO = "mantenimiento"


class EstadoVuelo(str, Enum):
    """Estados del ciclo de vida de un vuelo."""
    PLANIFICADO = "planificado"
    EN_RUTA = "en_ruta"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"
    EMERGENCIA = "emergencia"


class EstadoEntrega(str, Enum):
    """Estados del ciclo de vida de una entrega."""
    PENDIENTE = "pendiente"
    ASIGNADA = "asignada"
    EN_RUTA = "en_ruta"
    ENTREGADO = "entregado"
    FALLIDO = "fallido"


class TipoEntrega(str, Enum):
    """Tipos de carga con sus niveles de prioridad asociados."""
    MEDICINA = "medicina"           # Prioridad: 10
    ALIMENTOS = "alimentos"         # Prioridad: 7
    FARMACIA = "farmacia"           # Prioridad: 5
    GENERAL = "general"             # Prioridad: 1

    @property
    def prioridad(self) -> int:
        prioridades = {
            TipoEntrega.MEDICINA: 10,
            TipoEntrega.ALIMENTOS: 7,
            TipoEntrega.FARMACIA: 5,
            TipoEntrega.GENERAL: 1,
        }
        return prioridades[self]


class TipoZona(str, Enum):
    """Tipos de zona restringida según duración."""
    PERMANENTE = "permanente"
    TEMPORAL = "temporal"