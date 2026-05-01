/**
 * Gestor de la interfaz de usuario
 */
class UIManager {
    constructor() {
        this.selectedDrone = null;
        this.eventLogMaxItems = 100;
        this.initEventListeners();
    }

    initEventListeners() {
        // Botón simular vuelo
        document.getElementById('btn-simular')?.addEventListener('click', () => {
            this.simularVuelo();
        });

        // Botón emergencia
        document.getElementById('btn-emergencia')?.addEventListener('click', () => {
            this.activarEmergenciaGlobal();
        });

        // Filtros de entregas
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.filtrarEntregas(e.target.dataset.filter);
            });
        });

        // Controles de capas
        document.querySelectorAll('.layer-toggle input').forEach(toggle => {
            toggle.addEventListener('change', (e) => {
                const layer = e.target.id.replace('layer-', '');
                mapManager.toggleLayer(layer, e.target.checked);
            });
        });
    }

    // ============================================================
    // ACTUALIZACIÓN DE LISTAS
    // ============================================================
    
    updateDroneList(drones) {
        const container = document.getElementById('drone-list');
        if (!container) return;

        container.innerHTML = '';
        
        drones.forEach(dron => {
            const item = document.createElement('div');
            item.className = `drone-item ${dron.estado}`;
            if (dron.conflicto) item.classList.add('conflicto');
            
            const bateriaColor = dron.bateria_porcentaje > 50 ? 'var(--color-success)' : 
                                dron.bateria_porcentaje > 20 ? 'var(--color-warning)' : 'var(--color-danger)';
            
            item.innerHTML = `
                <div class="drone-header">
                    <span class="drone-id">${dron.numero_serie || dron.id}</span>
                    <span class="drone-status status-${dron.estado}">${dron.estado}</span>
                </div>
                <div class="drone-info">
                    <span class="battery-indicator">
                        <div class="battery-bar-mini">
                            <div class="battery-level-mini" style="width: ${dron.bateria_porcentaje}%; background: ${bateriaColor};"></div>
                        </div>
                        ${dron.bateria_porcentaje.toFixed(0)}%
                    </span>
                    <span><i class="fas fa-cube"></i> ${dron.capacidad_carga_kg}kg</span>
                    <span><i class="fas fa-clock"></i> ${dron.horas_vuelo_acumuladas?.toFixed(1) || 0}h</span>
                </div>
            `;
            
            item.addEventListener('click', () => {
                document.querySelectorAll('.drone-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                this.showDroneInfo(dron);
                
                // Centrar mapa en el dron
                if (dron.posicion || (dron.lat && dron.lng)) {
                    const pos = dron.posicion ? 
                        [dron.posicion.lat, dron.posicion.lng] : 
                        [dron.lat, dron.lng];
                    mapManager.map.setView(pos, 16);
                }
            });
            
            container.appendChild(item);
        });

        // Actualizar contadores
        document.getElementById('count-drones').textContent = drones.length;
        document.getElementById('stat-disponibles').textContent = drones.filter(d => d.estado === 'disponible').length;
        document.getElementById('stat-en-vuelo').textContent = drones.filter(d => d.estado === 'en_vuelo').length;
        document.getElementById('stat-mantenimiento').textContent = drones.filter(d => d.estado === 'mantenimiento').length;
    }

    updateDeliveryList(entregas) {
        const container = document.getElementById('delivery-list');
        if (!container) return;

        container.innerHTML = '';
        
        entregas.forEach(entrega => {
            const item = document.createElement('div');
            item.className = 'delivery-item';
            item.dataset.tipo = entrega.tipo;
            item.dataset.estado = entrega.estado;
            
            const prioridadClass = `priority-${entrega.prioridad}`;
            
            item.innerHTML = `
                <div class="delivery-header">
                    <span class="delivery-id">${entrega.numero_pedido}</span>
                    <span class="priority-badge ${prioridadClass}">${entrega.tipo}</span>
                </div>
                <div class="delivery-info">
                    <span><i class="fas fa-weight-hanging"></i> ${entrega.paquete?.peso_kg || 0}kg</span>
                    <span><i class="fas fa-flag"></i> ${entrega.estado}</span>
                    <span>Score: ${entrega.score_actual?.toFixed(1) || entrega.prioridad}</span>
                </div>
            `;
            
            item.addEventListener('click', () => {
                // Mostrar ruta en el mapa si tiene vuelo asignado
                if (entrega.vuelo_asignado_id) {
                    // Solicitar waypoints del vuelo
                    api.getVuelo(entrega.vuelo_asignado_id).then(vuelo => {
                        if (vuelo.data?.plan_vuelo?.waypoints) {
                            mapManager.drawRuta(
                                entrega.vuelo_asignado_id,
                                vuelo.data.plan_vuelo.waypoints,
                                entrega.tipo
                            );
                        }
                    });
                }
            });
            
            container.appendChild(item);
        });

        document.getElementById('count-entregas').textContent = entregas.length;
    }

    updateAlertList(alertas) {
        const container = document.getElementById('alert-list');
        if (!container) return;

        container.innerHTML = '';
        
        alertas.forEach(alerta => {
            const item = document.createElement('div');
            item.className = `alert-item ${alerta.severidad === 'alta' ? 'critica' : ''}`;
            
            const icono = alerta.tipo === 'bateria_baja' ? 'fa-battery-quarter' :
                         alerta.tipo === 'conflicto' ? 'fa-exclamation-triangle' :
                         alerta.tipo === 'mantenimiento_proximo' ? 'fa-tools' :
                         'fa-info-circle';
            
            item.innerHTML = `
                <div class="alert-severity" style="color: ${alerta.severidad === 'alta' ? 'var(--color-danger)' : 'var(--color-warning)'};">
                    <i class="fas ${icono}"></i> ${alerta.tipo}
                </div>
                <div class="alert-message">${alerta.mensaje}</div>
                <div class="alert-time">${new Date().toLocaleTimeString()}</div>
            `;
            
            container.appendChild(item);
        });

        document.getElementById('count-alertas').textContent = alertas.length;
    }

    // ============================================================
    // PANEL DE INFORMACIÓN DEL DRON
    // ============================================================
    
    showDroneInfo(dron) {
        this.selectedDrone = dron;
        const popup = document.getElementById('drone-info-popup');
        if (!popup) return;

        popup.style.display = 'block';
        
        document.getElementById('popup-drone-name').textContent = `Dron ${dron.numero_serie || dron.id}`;
        document.getElementById('popup-drone-status').textContent = dron.estado;
        document.getElementById('popup-drone-status').className = `info-value status-${dron.estado}`;
        
        const bateria = dron.bateria_porcentaje || dron.bateria || 0;
        document.getElementById('popup-battery-level').style.width = `${bateria}%`;
        document.getElementById('popup-battery-text').textContent = `${bateria.toFixed(1)}%`;
        
        document.getElementById('popup-altitude').textContent = `${(dron.altitud || dron.alt || 0).toFixed(1)}m`;
        document.getElementById('popup-speed').textContent = `${(dron.velocidad || 0).toFixed(1)} m/s`;
        document.getElementById('popup-delivery').textContent = dron.entrega_actual || 'Sin asignar';
    }

    // ============================================================
    // LOG DE EVENTOS
    // ============================================================
    
    addEventLog(tipo, data) {
        const container = document.getElementById('event-log');
        if (!container) return;

        const item = document.createElement('div');
        item.className = 'event-item';
        
        const tipoClass = tipo.toLowerCase().includes('posicion') ? 'posicion' :
                         tipo.toLowerCase().includes('alerta') ? 'alerta' :
                         tipo.toLowerCase().includes('despego') ? 'despego' :
                         tipo.toLowerCase().includes('entrega') ? 'entrega' : 'evento';
        
        const time = new Date().toLocaleTimeString('es-ES', { hour12: false });
        
        item.innerHTML = `
            <span class="event-time">${time}</span>
            <span class="event-type ${tipoClass}">${tipo}</span>
            <span class="event-data">${JSON.stringify(data).substring(0, 100)}...</span>
        `;
        
        container.insertBefore(item, container.firstChild);
        
        // Limitar items
        while (container.children.length > this.eventLogMaxItems) {
            container.removeChild(container.lastChild);
        }
    }

    clearEventLog() {
        const container = document.getElementById('event-log');
        if (container) container.innerHTML = '';
    }

    // ============================================================
    // MODALES
    // ============================================================
    
    showModal(modalId) {
        document.getElementById(modalId).style.display = 'flex';
    }

    closeModal(modalId) {
        document.getElementById(modalId).style.display = 'none';
    }

    // ============================================================
    // ACCIONES
    // ============================================================
    
    async simularVuelo() {
        try {
            // Obtener un dron disponible
            const drones = await api.getDronesDisponibles();
            if (!drones || drones.length === 0) {
                alert('No hay drones disponibles para simular');
                return;
            }

            const dron = drones[0];
            
            // Crear entrega de prueba
            const entrega = await api.crearEntrega({
                numero_pedido: `SIM-${Date.now()}`,
                tipo: 'general',
                paquete: { peso_kg: 1.0, dimensiones_cm: '20x20x10', fragil: false },
                direccion_origen: { latitud: -16.5000, longitud: -68.1500, altitud: 0 },
                direccion_destino: { latitud: -16.5200, longitud: -68.1700, altitud: 0, instrucciones: 'Simulación' },
            });

            // Asignar entrega
            await api.asignarEntrega(entrega.data.id);

            this.addEventLog('Simulación', { mensaje: 'Vuelo simulado iniciado', dron: dron.numero_serie });

        } catch (error) {
            console.error('Error en simulación:', error);
            alert('Error al simular vuelo: ' + error.message);
        }
    }

    async activarEmergenciaGlobal() {
        if (!confirm('¿Activar emergencia global? Esto aterrizará todos los drones en vuelo.')) {
            return;
        }

        try {
            const vuelos = await api.getVuelosActivos();
            for (const vuelo of vuelos) {
                await api.emergenciaVuelo(vuelo.id, 'Emergencia global activada por operador');
            }
            this.addEventLog('Emergencia', { mensaje: 'Emergencia global activada' });
        } catch (error) {
            console.error('Error en emergencia:', error);
        }
    }

    async forzarAterrizaje() {
        if (!this.selectedDrone) return;
        
        if (!confirm(`¿Forzar aterrizaje del dron ${this.selectedDrone.numero_serie}?`)) {
            return;
        }

        try {
            // Encontrar vuelo activo del dron
            const vuelos = await api.getVuelosActivos();
            const vuelo = vuelos.find(v => v.dron_id === this.selectedDrone.id);
            
            if (vuelo) {
                await api.cancelarVuelo(vuelo.id, 'Aterrizaje forzado por operador');
                this.addEventLog('Aterrizaje', { dron: this.selectedDrone.numero_serie });
            }
        } catch (error) {
            console.error('Error en aterrizaje:', error);
        }
    }

    async activarEmergencia() {
        if (!this.selectedDrone) return;
        
        if (!confirm(`¿Activar emergencia para el dron ${this.selectedDrone.numero_serie}?`)) {
            return;
        }

        try {
            const vuelos = await api.getVuelosActivos();
            const vuelo = vuelos.find(v => v.dron_id === this.selectedDrone.id);
            
            if (vuelo) {
                await api.emergenciaVuelo(vuelo.id, 'Emergencia activada por operador');
            }
        } catch (error) {
            console.error('Error en emergencia:', error);
        }
    }

    filtrarEntregas(filtro) {
        const items = document.querySelectorAll('.delivery-item');
        items.forEach(item => {
            let visible = true;
            if (filtro === 'criticas') {
                visible = item.dataset.tipo === 'medicina';
            } else if (filtro === 'pendientes') {
                visible = item.dataset.estado === 'pendiente';
            }
            item.style.display = visible ? 'block' : 'none';
        });
    }

    toggleEventLog() {
        const panel = document.querySelector('.bottom-panel');
        panel.classList.toggle('collapsed');
    }
}

// Instancia global
const uiManager = new UIManager();