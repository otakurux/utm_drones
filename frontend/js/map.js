/**
 * Gestor del mapa interactivo con Leaflet.js
 */
class MapManager {
    constructor(containerId = 'map') {
        this.map = null;
        this.containerId = containerId;
        this.markers = new Map();        // dron_id -> marker
        this.rutas = new Map();          // vuelo_id -> polyline
        this.zonas = new Map();          // zona_id -> polygon
        this.geocercas = new Map();      // vuelo_id -> circle
        this.trails = new Map();         // dron_id -> array de puntos
        
        // Iconos personalizados
        this.icons = this.createIcons();
    }

    init() {
        // Inicializar mapa centrado en La Paz, Bolivia
        this.map = L.map(this.containerId, {
            center: [-16.5000, -68.1500],
            zoom: 13,
            zoomControl: true,
            attributionControl: false,
        });

        // Capa base oscura (CartoDB Dark Matter)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; OpenStreetMap &copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 20,
        }).addTo(this.map);

        // Capa de satélite opcional
        this.satelliteLayer = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Esri',
            maxZoom: 18,
        });

        // Control de capas
        const baseMaps = {
            "Oscuro": this.map._layers[Object.keys(this.map._layers)[0]], // layer base
            "Satélite": this.satelliteLayer,
        };
        
        L.control.layers(baseMaps, null, {
            position: 'topright',
            collapsed: true,
        }).addTo(this.map);

        // Escalar al cambiar tamaño
        window.addEventListener('resize', () => {
            this.map.invalidateSize();
        });

        return this;
    }

    createIcons() {
        const createDroneIcon = (color, estado) => {
            return L.divIcon({
                className: 'drone-marker',
                html: `
                    <div style="
                        width: 24px;
                        height: 24px;
                        background: ${color};
                        border: 2px solid white;
                        border-radius: 50%;
                        box-shadow: 0 0 10px ${color};
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        animation: ${estado === 'conflicto' ? 'pulse 1s infinite' : 'none'};
                    ">
                        <i class="fas fa-helicopter" style="font-size: 10px; color: white;"></i>
                    </div>
                `,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
                popupAnchor: [0, -12],
            });
        };

        return {
            disponible: createDroneIcon('#10b981', 'disponible'),
            en_vuelo: createDroneIcon('#2563eb', 'en_vuelo'),
            cargando: createDroneIcon('#f59e0b', 'cargando'),
            mantenimiento: createDroneIcon('#ef4444', 'mantenimiento'),
            conflicto: createDroneIcon('#ef4444', 'conflicto'),
        };
    }

    // ============================================================
    // DRONES
    // ============================================================
    
    addOrUpdateDrone(dron) {
        const id = dron.id || dron.dron_id;
        const pos = [dron.lat || dron.latitud, dron.lng || dron.longitud];
        const estado = dron.estado || 'disponible';
        const isConflicto = dron.conflicto || false;
        
        const icon = isConflicto ? this.icons.conflicto : (this.icons[estado] || this.icons.disponible);

        if (this.markers.has(id)) {
            // Actualizar posición existente
            const marker = this.markers.get(id);
            marker.setLatLng(pos);
            marker.setIcon(icon);
            
            // Actualizar popup
            this.updateDronePopup(marker, dron);
            
            // Actualizar trail
            this.updateTrail(id, pos);
        } else {
            // Crear nuevo marcador
            const marker = L.marker(pos, {
                icon: icon,
                title: `Dron ${dron.numero_serie || id}`,
            }).addTo(this.map);

            // Popup
            const popupContent = this.createDronePopupContent(dron);
            marker.bindPopup(popupContent);

            // Evento click
            marker.on('click', () => {
                this.onDroneClick(dron);
            });

            this.markers.set(id, marker);
            this.trails.set(id, [pos]);
        }
    }

    updateTrail(dronId, newPos) {
        if (!this.trails.has(dronId)) {
            this.trails.set(dronId, []);
        }
        
        const trail = this.trails.get(dronId);
        trail.push(newPos);
        
        // Mantener solo últimos 20 puntos
        if (trail.length > 20) {
            trail.shift();
        }

        // Dibujar línea de trail
        const trailKey = `trail-${dronId}`;
        if (this.rutas.has(trailKey)) {
            this.rutas.get(trailKey).setLatLngs(trail);
        } else {
            const polyline = L.polyline(trail, {
                color: '#2563eb',
                weight: 2,
                opacity: 0.5,
                dashArray: '5, 5',
            }).addTo(this.map);
            this.rutas.set(trailKey, polyline);
        }
    }

    removeDrone(dronId) {
        if (this.markers.has(dronId)) {
            this.map.removeLayer(this.markers.get(dronId));
            this.markers.delete(dronId);
        }
        
        const trailKey = `trail-${dronId}`;
        if (this.rutas.has(trailKey)) {
            this.map.removeLayer(this.rutas.get(trailKey));
            this.rutas.delete(trailKey);
        }
        
        this.trails.delete(dronId);
    }

    createDronePopupContent(dron) {
        const bateria = dron.bateria_porcentaje || dron.bateria || 100;
        const bateriaColor = bateria > 50 ? '#10b981' : bateria > 20 ? '#f59e0b' : '#ef4444';
        
        return `
            <div style="min-width: 200px;">
                <h4 style="margin: 0 0 8px 0;">Dron ${dron.numero_serie || dron.id}</h4>
                <div style="font-size: 12px; color: #94a3b8;">
                    <div>Estado: <span style="color: white; text-transform: uppercase;">${dron.estado}</span></div>
                    <div>Batería: <span style="color: ${bateriaColor}; font-weight: bold;">${bateria.toFixed(1)}%</span></div>
                    <div>Altitud: ${(dron.alt || dron.altitud || 0).toFixed(1)}m</div>
                    <div>Velocidad: ${(dron.velocidad || 0).toFixed(1)} m/s</div>
                </div>
            </div>
        `;
    }

    updateDronePopup(marker, dron) {
        const content = this.createDronePopupContent(dron);
        marker.setPopupContent(content);
    }

    onDroneClick(dron) {
        // Mostrar panel de información
        window.uiManager?.showDroneInfo(dron);
    }

    // ============================================================
    // RUTAS
    // ============================================================
    
    drawRuta(vueloId, waypoints, tipo = 'general') {
        // Remover ruta existente
        this.removeRuta(vueloId);
        
        if (!waypoints || waypoints.length < 2) return;

        const latlngs = waypoints.map(wp => [wp.lat || wp.latitud, wp.lng || wp.longitud]);
        
        const color = tipo === 'medicina' ? '#ef4444' : 
                      tipo === 'alimentos' ? '#f59e0b' : 
                      tipo === 'farmacia' ? '#06b6d4' : '#64748b';

        const polyline = L.polyline(latlngs, {
            color: color,
            weight: 3,
            opacity: 0.8,
            className: 'ruta-animada',
        }).addTo(this.map);

        // Flechas de dirección
        const decorator = L.polylineDecorator(polyline, {
            patterns: [
                {
                    offset: '5%',
                    repeat: '10%',
                    symbol: L.Symbol.arrowHead({
                        pixelSize: 10,
                        polygon: false,
                        pathOptions: {
                            stroke: true,
                            color: color,
                            weight: 2,
                        }
                    })
                }
            ]
        }).addTo(this.map);

        this.rutas.set(vueloId, { line: polyline, decorator: decorator });
    }

    removeRuta(vueloId) {
        if (this.rutas.has(vueloId)) {
            const ruta = this.rutas.get(vueloId);
            this.map.removeLayer(ruta.line);
            if (ruta.decorator) this.map.removeLayer(ruta.decorator);
            this.rutas.delete(vueloId);
        }
    }

    // ============================================================
    // ZONAS RESTRINGIDAS
    // ============================================================
    
    drawZona(zona) {
        const id = zona.id;
        
        // Remover zona existente
        this.removeZona(id);

        const coords = zona.coordenadas.map(c => [c[0], c[1]]);
        
        const polygon = L.polygon(coords, {
            color: '#ef4444',
            weight: 2,
            fillColor: '#ef4444',
            fillOpacity: 0.15,
            dashArray: '5, 5',
        }).addTo(this.map);

        // Tooltip
        polygon.bindTooltip(`
            <div style="font-size: 12px;">
                <strong>${zona.nombre}</strong><br>
                ${zona.codigo}<br>
                Tipo: ${zona.tipo}<br>
                Alt: ${zona.altitud_min}m - ${zona.altitud_max}m
            </div>
        `, {
            permanent: false,
            direction: 'top',
        });

        this.zonas.set(id, polygon);
    }

    removeZona(zonaId) {
        if (this.zonas.has(zonaId)) {
            this.map.removeLayer(this.zonas.get(zonaId));
            this.zonas.delete(zonaId);
        }
    }

    // ============================================================
    // GEOCERCAS
    // ============================================================
    
    drawGeocerca(vueloId, centro, radio = 20) {
        this.removeGeocerca(vueloId);
        
        const circle = L.circle(centro, {
            radius: radio,
            color: '#10b981',
            weight: 1,
            fillColor: '#10b981',
            fillOpacity: 0.1,
            dashArray: '3, 3',
        }).addTo(this.map);
        
        this.geocercas.set(vueloId, circle);
    }

    removeGeocerca(vueloId) {
        if (this.geocercas.has(vueloId)) {
            this.map.removeLayer(this.geocercas.get(vueloId));
            this.geocercas.delete(vueloId);
        }
    }

    // ============================================================
    // UTILIDADES
    // ============================================================
    
    fitBounds() {
        const bounds = [];
        this.markers.forEach(marker => {
            bounds.push(marker.getLatLng());
        });
        
        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    clearAll() {
        // Limpiar marcadores
        this.markers.forEach(marker => this.map.removeLayer(marker));
        this.markers.clear();
        
        // Limpiar rutas
        this.rutas.forEach(ruta => {
            this.map.removeLayer(ruta.line);
            if (ruta.decorator) this.map.removeLayer(ruta.decorator);
        });
        this.rutas.clear();
        
        // Limpiar zonas
        this.zonas.forEach(zona => this.map.removeLayer(zona));
        this.zonas.clear();
        
        // Limpiar geocercas
        this.geocercas.forEach(geo => this.map.removeLayer(geo));
        this.geocercas.clear();
        
        this.trails.clear();
    }

    toggleLayer(tipo, visible) {
        switch(tipo) {
            case 'drones':
                this.markers.forEach(m => {
                    visible ? this.map.addLayer(m) : this.map.removeLayer(m);
                });
                break;
            case 'rutas':
                this.rutas.forEach(r => {
                    visible ? this.map.addLayer(r.line) : this.map.removeLayer(r.line);
                    if (r.decorator) {
                        visible ? this.map.addLayer(r.decorator) : this.map.removeLayer(r.decorator);
                    }
                });
                break;
            case 'zonas':
                this.zonas.forEach(z => {
                    visible ? this.map.addLayer(z) : this.map.removeLayer(z);
                });
                break;
            case 'geocercas':
                this.geocercas.forEach(g => {
                    visible ? this.map.addLayer(g) : this.map.removeLayer(g);
                });
                break;
        }
    }
}

// Instancia global
const mapManager = new MapManager();