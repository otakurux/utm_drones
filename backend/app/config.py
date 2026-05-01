"""config""" 
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Configuración centralizada del sistema UTM."""
    
    # MongoDB
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "utm_drones")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30  # segundos
    
    # Aplicación
    APP_NAME: str = "UTM Drones"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"


config = Config()