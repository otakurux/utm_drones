/**
 * Aplicación principal UTM Drones
 * Coordina API, WebSocket, Mapa y UI
 */
class UTMApp {
    constructor() {
        this.updateInterval = null;
        this.posicionInterval = null;
    }

    async init() {
        console.log('🚀 Iniciando UTM Drones...');

        // Inicializar mapa
        mapManager.init();
        
        // Verificar conexión API
        await this.checkAPIHealth();
        
        // Conectar WebSocket
        wsManager.connect();
        
        // Configurar listeners de WebSocket
        this.setupWebSocketListeners();
        
        // Cargar datos iniciales
        await this.loadInitialData();
        
        // Iniciar actualizaciones periódicas
        this.startPeriodicUpdates();
        
        console.log('✅ UTM Drones iniciado correctamente');
    }

    async checkAPIHealth() {
        try {
            const health = await api.healthCheck();
            const indicator = document.getElementById('api-status');
            if (indicator) {
                const dot = indicator.querySelector('.dot');
                if (health.status === 'saludable') {
                    dot.classList.remove('offline');
                    dot.classList.add('online');
                }
            }
        } catch (error) {
            console.error('API no disponible:', error);
            this.showNotification('API no disponible. Algunas funciones pueden no funcionar.', 'warning');
        }
    }

    setupWebSocketListeners() {
        // Posiciones en tiempo real
        wsManager.on('PosicionActualizada', (data) => {
            this.handlePosicionActualizada(data);
        });

        // Alertas
        wsManager.on('Alerta', (data) => {
            this.handleAlerta(data);
        });

        // Eventos de dominio
        wsManager.on('DronDespego', (data) => {
            uiManager.addEventLog('Despegue', data);
            this.showNotification(`Dron ${data.dron_id} despegó`, 'info');
        });

        wsManager.on('EntregaCompletada', (data) => {
            uiManager.addEventLog('Entrega Completada', data);
            this.showNotification('Entrega completada exitosamente', 'success');
            this.refreshDashboard();
        });

        wsManager.on('ConflictoDetectado', (data) => {
            uiManager.addEventLog('Conflicto', data);
            this.showNotification('¡Conflicto de ruta detectado!', 'error');
            this.handleConflicto(data);
        });

        // Heartbeat
        wsManager.on('heartbeat', (data) => {
            // console.log('Heartbeat recibido');
        });

        // Conexión
        wsManager.on('connected', () => {
            this.showNotification('Conectado en tiempo real', 'success');
        });
    }

    // ============================================================
    // MANEJADORES DE EVENTOS WEBSOCKET
    // ============================================================
    
    handlePosicionActualizada(data) {
        // Actualizar marcador en el mapa
        mapManager.addOrUpdateDrone({
            id: data.dron_id,
            lat: data.latitud,
            lng: data.longitud,
            alt: data.altitud,
            velocidad: data.velocidad,
            bateria: data.bateria,
            estado: 'en_vuelo',
        });

        // Actualizar panel si es el dron seleccionado
        if (uiManager.selectedDrone && uiManager.selectedDrone.id === data.dron_id) {
            uiManager.showDroneInfo({
                ...uiManager.selectedDrone,
                latitud: data.latitud,
                longitud: data.longitud,
                altitud: data.altitud,
                velocidad: data.velocidad,
                bateria_porcentaje: data.bateria,
            });
        }

        // Log cada 5 segundos (no cada 500ms)
        if (Math.random() < 0.1) {
            uiManager.addEventLog('Posición', {
                dron: data.dron_id.substring(0, 8),
                pos: `${data.latitud.toFixed(4)}, ${data.longitud.toFixed(4)}`,
            });
        }
    }

    handleAlerta(data) {
        // Recargar alertas
        this.refreshAlertas();
        
        // Sonido de alerta si es crítica
        if (data.severidad === 'alta' || data.tipo === 'EMERGENCIA') {
            this.playAlertSound();
        }
    }

    handleConflicto(data) {
        // Marcar drones en conflicto
        const dronA = mapManager.markers.get(data.dron_a_id);
        const dronB = mapManager.markers.get(data.dron_b_id);
        
        if (dronA) dronA.getElement()?.classList.add('conflicto');
        if (dronB) dronB.getElement()?.classList.add('conflicto');
    }

    // ============================================================
    // CARGA DE DATOS
    // ============================================================
    
    async loadInitialData() {
        try {
            // Cargar drones
            const drones = await api.getDrones();
            if (drones) {
                uiManager.updateDroneList(drones);
                drones.forEach(d => {
                    if (d.posicion) {
                        mapManager.addOrUpdateDrone({
                            ...d,
                            lat: d.posicion.lat,
                            lng: d.posicion.lng,
                        });
                    }
                });
            }

            // Cargar entregas
            const entregas = await api.getEntregasPendientes();
            if (entregas) {
                uiManager.updateDeliveryList(entregas);
            }

            // Cargar zonas restringidas
            const zonas = await api.getZonasActivas();
            if (zonas) {
                zonas.forEach(z => mapManager.drawZona(z));
            }

            // Cargar estadísticas
            await this.refreshDashboard();

        } catch (error) {
            console.error('Error cargando datos iniciales:', error);
        }
    }

    // ============================================================
    // ACTUALIZACIONES PERIÓDICAS
    // ============================================================
    
    startPeriodicUpdates() {
        // Actualizar cada 5 segundos
        this.updateInterval = setInterval(() => {
            this.refreshDashboard();
            this.refreshDroneList();
        }, 5000);

        // Actualizar posiciones cada 2 segundos
        this.posicionInterval = setInterval(() => {
            this.refreshPosiciones();
        }, 2000);
    }

    stopPeriodicUpdates() {
        if (this.updateInterval) clearInterval(this.updateInterval);
        if (this.posicionInterval) clearInterval(this.posicionInterval);
    }

    async refreshDashboard() {
        try {
            const stats = await api.getEstadisticas();
            if (stats?.data) {
                this.updateDashboardStats(stats.data);
            }
        } catch (error) {
            console.error('Error actualizando dashboard:', error);
        }
    }

    async refreshDroneList() {
        try {
            const drones = await api.getDrones();
            if (drones) {
                uiManager.updateDroneList(drones);
            }
        } catch (error) {
            console.error('Error actualizando drones:', error);
        }
    }

    async refreshPosiciones() {
        try {
            const posiciones = await api.getTraficoActivo();
            if (posiciones?.data?.posiciones_drones) {
                posiciones.data.posiciones_drones.forEach(pos => {
                    mapManager.addOrUpdateDrone({
                        id: pos.dron_id,
                        lat: pos.lat,
                        lng: pos.lng,
                        alt: pos.alt,
                        velocidad: pos.velocidad,
                        bateria: pos.bateria,
                        estado: 'en_vuelo',
                    });
                });
            }
        } catch (error) {
            console.error('Error actualizando posiciones:', error);
        }
    }

    async refreshAlertas() {
        try {
            const alertas = await api.getAlertas();
            if (alertas?.data?.alertas) {
                uiManager.updateAlertList(alertas.data.alertas);
            }
        } catch (error) {
            console.error('Error actualizando alertas:', error);
        }
    }

    updateDashboardStats(data) {
        // Actualizar contadores en la UI
        const flota = data.estadisticas?.estado_flota;
        if (flota) {
            document.getElementById('stat-disponibles').textContent = flota.disponibles;
            document.getElementById('stat-en-vuelo').textContent = flota.en_vuelo;
            document.getElementById('stat-mantenimiento').textContent = flota.mantenimiento;
        }

        // Actualizar alertas
        if (data.alertas) {
            uiManager.updateAlertList(data.alertas);
        }
    }

    // ============================================================
    // NOTIFICACIONES
    // ============================================================
    
    showNotification(mensaje, tipo = 'info') {
        // Crear toast notification
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            z-index: 3000;
            animation: slideIn 0.3s ease;
            max-width: 300px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        `;
        
        const colors = {
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b',
            info: '#2563eb',
        };
        
        toast.style.background = colors[tipo] || colors.info;
        toast.textContent = mensaje;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    playAlertSound() {
        // Crear beep simple
        const audio = new AudioContext();
        const oscillator = audio.createOscillator();
        const gainNode = audio.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audio.destination);
        
        oscillator.frequency.value = 800;
        oscillator.type = 'square';
        
        gainNode.gain.setValueAtTime(0.1, audio.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audio.currentTime + 0.5);
        
        oscillator.start(audio.currentTime);
        oscillator.stop(audio.currentTime + 0.5);
    }
}

// ============================================================
// INICIALIZACIÓN
// ============================================================

// Funciones globales para eventos HTML
function closeDronePopup() {
    document.getElementById('drone-info-popup').style.display = 'none';
    uiManager.selectedDrone = null;
}

function forzarAterrizaje() {
    uiManager.forzarAterrizaje();
}

function activarEmergencia() {
    uiManager.activarEmergencia();
}

function closeModal(modalId) {
    uiManager.closeModal(modalId);
}

function clearEventLog() {
    uiManager.clearEventLog();
}

function toggleEventLog() {
    uiManager.toggleEventLog();
}

async function crearEntrega() {
    const form = document.getElementById('form-nueva-entrega');
    const formData = new FormData(form);
    
    const entrega = {
        numero_pedido: formData.get('numero_pedido'),
        tipo: formData.get('tipo'),
        paquete: {
            peso_kg: parseFloat(formData.get('peso_kg')),
            fragil: formData.has('fragil'),
        },
        direccion_origen: {
            latitud: parseFloat(formData.get('origen_lat')),
            longitud: parseFloat(formData.get('origen_lng')),
        },
        direccion_destino: {
            latitud: parseFloat(formData.get('destino_lat')),
            longitud: parseFloat(formData.get('destino_lng')),
            instrucciones: formData.get('instrucciones'),
        },
    };
    
    try {
        const result = await api.crearEntrega(entrega);
        uiManager.showNotification('Entrega creada exitosamente', 'success');
        uiManager.closeModal('modal-nueva-entrega');
        form.reset();
        
        // Recargar lista
        const entregas = await api.getEntregasPendientes();
        uiManager.updateDeliveryList(entregas);
        
    } catch (error) {
        uiManager.showNotification('Error: ' + error.message, 'error');
    }
}

// Iniciar aplicación cuando DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
    const app = new UTMApp();
    app.init();
});