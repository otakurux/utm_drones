/**
 * Cliente API para comunicación REST con el backend
 */
class APIClient {
    constructor(baseURL = 'http://localhost:8000') {
        this.baseURL = baseURL;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        };

        if (config.body && typeof config.body === 'object') {
            config.body = JSON.stringify(config.body);
        }

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || data.error || `HTTP ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            throw error;
        }
    }

    // ============================================================
    // DRONES
    // ============================================================
    
    async getDrones(estado = null) {
        const params = estado ? `?estado=${estado}` : '';
        return this.request(`/drones${params}`);
    }

    async getDronesDisponibles() {
        return this.request('/drones/disponibles');
    }

    async getDron(id) {
        return this.request(`/drones/${id}`);
    }

    async getDronPosicion(id) {
        return this.request(`/drones/${id}/posicion`);
    }

    async crearDron(dron) {
        return this.request('/drones', {
            method: 'POST',
            body: dron,
        });
    }

    async recargarDron(id) {
        return this.request(`/drones/${id}/recargar`, { method: 'POST' });
    }

    async enviarMantenimiento(id, motivo, detalles = '') {
        return this.request(`/drones/${id}/mantenimiento?motivo=${encodeURIComponent(motivo)}&detalles=${encodeURIComponent(detalles)}`, {
            method: 'POST',
        });
    }

    // ============================================================
    // ENTREGAS
    // ============================================================
    
    async getEntregas(estado = null, tipo = null) {
        let params = new URLSearchParams();
        if (estado) params.append('estado', estado);
        if (tipo) params.append('tipo', tipo);
        const query = params.toString() ? `?${params.toString()}` : '';
        return this.request(`/entregas${query}`);
    }

    async getEntregasPendientes() {
        return this.request('/entregas/pendientes');
    }

    async getEntregasCriticas() {
        return this.request('/entregas/criticas');
    }

    async crearEntrega(entrega) {
        return this.request('/entregas', {
            method: 'POST',
            body: entrega,
        });
    }

    async asignarEntrega(id) {
        return this.request(`/entregas/${id}/asignar`, { method: 'POST' });
    }

    async completarEntrega(id) {
        return this.request(`/entregas/${id}/completar`, { method: 'POST' });
    }

    // ============================================================
    // VUELOS
    // ============================================================
    
    async getVuelos(estado = null) {
        const params = estado ? `?estado=${estado}` : '';
        return this.request(`/vuelos${params}`);
    }

    async getVuelosActivos() {
        return this.request('/vuelos/activos');
    }

    async crearVuelo(vuelo) {
        return this.request('/vuelos', {
            method: 'POST',
            body: vuelo,
        });
    }

    async despegarVuelo(id) {
        return this.request(`/vuelos/${id}/despegar`, { method: 'POST' });
    }

    async cancelarVuelo(id, motivo = '') {
        return this.request(`/vuelos/${id}/cancelar?motivo=${encodeURIComponent(motivo)}`, {
            method: 'POST',
        });
    }

    async emergenciaVuelo(id, motivo) {
        return this.request(`/vuelos/${id}/emergencia?motivo=${encodeURIComponent(motivo)}`, {
            method: 'POST',
        });
    }

    // ============================================================
    // ZONAS
    // ============================================================
    
    async getZonas(soloActivas = false) {
        const params = soloActivas ? '?solo_activas=true' : '';
        return this.request(`/zonas${params}`);
    }

    async getZonasActivas() {
        return this.request('/zonas/activas');
    }

    async crearZona(zona) {
        return this.request('/zonas', {
            method: 'POST',
            body: zona,
        });
    }

    async desactivarZona(id) {
        return this.request(`/zonas/${id}/desactivar`, { method: 'PATCH' });
    }

    // ============================================================
    // DASHBOARD
    // ============================================================
    
    async getEstadisticas() {
        return this.request('/dashboard/estadisticas');
    }

    async getEstadoFlota() {
        return this.request('/dashboard/flota');
    }

    async getAlertas() {
        return this.request('/dashboard/alertas');
    }

    async getColaEntregas() {
        return this.request('/dashboard/cola-entregas');
    }

    async getTraficoActivo() {
        return this.request('/dashboard/trafico-activo');
    }

    // ============================================================
    // SALUD
    // ============================================================
    
    async healthCheck() {
        return this.request('/health');
    }
}

// Instancia global
const api = new APIClient();