Aquí tienes el README para levantar el backend:

---

# UTM Drones - Backend

Sistema de Gestión de Tráfico Aéreo para drones urbanos. Backend con FastAPI, MongoDB y Redis.

## Requisitos

- Python **3.11.x** (no usar 3.14)
- MongoDB 7.x corriendo en `localhost:27017`
- Redis 7.x corriendo en `localhost:6379`

## Instalación

```bash
# 1. Clonar y entrar al directorio
cd backend

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar (Windows)
venv\Scripts\activate

# 4. Instalar dependencias
pip install -r requirements.txt
```

## Levantar el servidor

```bash
uvicorn app.main:app --reload
```

La API estará disponible en `http://127.0.0.1:8000`

## Verificar servicios

- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

## Estructura

```
backend/
├── app/
│   ├── main.py              # Punto de entrada
│   ├── config.py            # Variables de entorno
│   ├── domain/              # Entidades, agregados, servicios DDD
│   ├── api/                 # Routes REST + WebSocket
│   └── infrastructure/      # Repositorios MongoDB/Redis
├── requirements.txt
└── venv/                    # Entorno virtual
```

## Variables de entorno (opcional)

Crea un `.env` en `backend/`:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=utm_drones
REDIS_HOST=localhost
REDIS_PORT=6379
```

---
