/**
 * Gestor de WebSocket para comunicación en tiempo real
 */
class WebSocketManager {
    constructor(url = 'ws://localhost:8000/ws') {
        this.url = url;
        this.ws = null;
        this.reconnectInterval = 5000;
        this.heartbeatInterval = 30000;
        this.heartbeatTimer = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.listeners = new Map();
        this.isConnected = false;
    }

    connect() {
        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                console.log('WebSocket conectado');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateStatus(true);
                
                // Suscribirse a canales
                this.subscribe(['posiciones', 'alertas', 'eventos', 'estadisticas']);
                
                // Iniciar heartbeat
                this.startHeartbeat();
                
                // Emitir evento
                this.emit('connected', {});
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('Error parseando mensaje:', e);
                }
            };

            this.ws.onclose = () => {
                console.log('WebSocket cerrado');
                this.isConnected = false;
                this.updateStatus(false);
                this.stopHeartbeat();
                this.attemptReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.emit('error', error);
            };

        } catch (error) {
            console.error('Error conectando WebSocket:', error);
            this.attemptReconnect();
        }
    }

    disconnect() {
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
    }

    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Máximo de reintentos alcanzado');
            this.emit('maxReconnectReached', {});
            return;
        }

        this.reconnectAttempts++;
        console.log(`Reintentando conexión (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

        setTimeout(() => {
            this.connect();
        }, this.reconnectInterval);
    }

    subscribe(canales) {
        if (this.isConnected) {
            this.send({
                accion: 'suscribir',
                canales: canales,
            });
        }
    }

    send(data) {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    startHeartbeat() {
        this.heartbeatTimer = setInterval(() => {
            this.send({ accion: 'ping' });
        }, this.heartbeatInterval);
    }

    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    handleMessage(data) {
        const tipo = data.tipo || 'unknown';
        
        // Emitir a listeners específicos
        this.emit(tipo, data.payload || data);
        
        // Emitir a listener genérico
        this.emit('message', data);
    }

    // Sistema de eventos
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }

    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`Error en listener de ${event}:`, e);
                }
            });
        }
    }

    updateStatus(connected) {
        const indicator = document.getElementById('ws-status');
        if (indicator) {
            const dot = indicator.querySelector('.dot');
            if (connected) {
                dot.classList.remove('offline');
                dot.classList.add('online');
            } else {
                dot.classList.remove('online');
                dot.classList.add('offline');
            }
        }
    }
}

// Instancia global
const wsManager = new WebSocketManager();