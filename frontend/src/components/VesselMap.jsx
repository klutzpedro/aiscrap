import { useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const VESSEL_COLORS = {
    'Cargo': '#10B981', 'General Cargo': '#10B981', 'Cargo Vessel': '#10B981',
    'Cargo - Hazardous A': '#10B981', 'Cargo - Hazardous B': '#10B981',
    'Cargo - Hazardous C': '#10B981', 'Cargo - Hazardous D': '#10B981',
    'Tanker': '#F43F5E', 'Crude Oil Tanker': '#F43F5E', 'Chemical Tanker': '#F43F5E',
    'Product Tanker': '#F43F5E', 'Oil/Chemical Tanker': '#F43F5E',
    'Container Ship': '#00A6FB', 'Bulk Carrier': '#F59E0B',
    'Passenger': '#A855F7', 'Fishing': '#06B6D4',
    'High Speed Craft': '#EC4899', 'Tug': '#8B5CF6', 'Tugs & Special Craft': '#8B5CF6',
    'Supply Vessel': '#14B8A6', 'Offshore Supply': '#14B8A6',
    'Special Craft': '#6366F1', 'LNG Carrier': '#F97316', 'LPG Carrier': '#F97316',
    'Vehicle Carrier': '#84CC16', 'Ro-Ro Cargo': '#84CC16', 'FPSO/FSO': '#D946EF',
};

function getColor(type) {
    if (!type) return '#94A3B8';
    if (VESSEL_COLORS[type]) return VESSEL_COLORS[type];
    const l = type.toLowerCase();
    if (l.includes('cargo')) return '#10B981';
    if (l.includes('tanker')) return '#F43F5E';
    if (l.includes('container')) return '#00A6FB';
    if (l.includes('bulk')) return '#F59E0B';
    if (l.includes('passenger')) return '#A855F7';
    if (l.includes('fish')) return '#06B6D4';
    if (l.includes('tug')) return '#8B5CF6';
    return '#94A3B8';
}

function getFlagUrl(code) {
    if (!code) return null;
    return `https://flagcdn.com/w40/${code.toLowerCase()}.png`;
}

// Custom Canvas layer that draws triangles for all vessels
const VesselCanvasLayer = L.Layer.extend({
    initialize(vessels) {
        this._vessels = vessels || [];
        this._canvas = null;
    },
    onAdd(map) {
        this._map = map;
        this._canvas = L.DomUtil.create('canvas', 'vessel-canvas');
        const pane = map.getPane('overlayPane');
        pane.appendChild(this._canvas);
        this._canvas.style.position = 'absolute';
        this._canvas.style.pointerEvents = 'none';
        map.on('moveend zoomend resize', this._redraw, this);
        this._redraw();
    },
    onRemove(map) {
        L.DomUtil.remove(this._canvas);
        map.off('moveend zoomend resize', this._redraw, this);
    },
    setVessels(vessels) {
        this._vessels = vessels || [];
        if (this._map) this._redraw();
    },
    _redraw() {
        const map = this._map;
        const size = map.getSize();
        const topLeft = map.containerPointToLayerPoint([0, 0]);
        L.DomUtil.setPosition(this._canvas, topLeft);
        this._canvas.width = size.x;
        this._canvas.height = size.y;
        const ctx = this._canvas.getContext('2d');
        ctx.clearRect(0, 0, size.x, size.y);
        const zoom = map.getZoom();
        const triSize = Math.max(3, Math.min(10, zoom));

        // Batch draw by color for performance
        const byColor = {};
        for (const v of this._vessels) {
            const pt = map.latLngToContainerPoint([v.latitude, v.longitude]);
            if (pt.x < -20 || pt.x > size.x + 20 || pt.y < -20 || pt.y > size.y + 20) continue;
            const color = getColor(v.vessel_type);
            if (!byColor[color]) byColor[color] = [];
            byColor[color].push({ x: pt.x, y: pt.y, h: (v.heading ?? v.course ?? 0) * Math.PI / 180 });
        }

        ctx.lineWidth = 0.5;
        ctx.strokeStyle = '#000';
        for (const [color, points] of Object.entries(byColor)) {
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.85;
            ctx.beginPath();
            for (const p of points) {
                const cos = Math.cos(p.h), sin = Math.sin(p.h);
                const tx = (dx, dy) => p.x + dx * cos - dy * sin;
                const ty = (dx, dy) => p.y + dx * sin + dy * cos;
                ctx.moveTo(tx(0, -triSize), ty(0, -triSize));
                ctx.lineTo(tx(triSize * 0.6, triSize * 0.7), ty(triSize * 0.6, triSize * 0.7));
                ctx.lineTo(tx(0, triSize * 0.3), ty(0, triSize * 0.3));
                ctx.lineTo(tx(-triSize * 0.6, triSize * 0.7), ty(-triSize * 0.6, triSize * 0.7));
                ctx.closePath();
            }
            ctx.fill();
            ctx.globalAlpha = 1;
            ctx.stroke();
        }
    }
});

// React component that manages the canvas layer + click popups
function VesselLayer({ vessels }) {
    const map = useMap();
    const layerRef = useRef(null);
    const popupRef = useRef(null);

    useEffect(() => {
        if (!layerRef.current) {
            layerRef.current = new VesselCanvasLayer(vessels);
            layerRef.current.addTo(map);
        } else {
            layerRef.current.setVessels(vessels);
        }
        return () => {
            if (layerRef.current) {
                map.removeLayer(layerRef.current);
                layerRef.current = null;
            }
        };
    }, [map, vessels]);

    // Handle click to show popup
    const handleClick = useCallback((e) => {
        const clickPt = e.containerPoint;
        const zoom = map.getZoom();
        const hitRadius = Math.max(8, 14 - zoom);
        let closest = null;
        let closestDist = Infinity;

        for (const v of vessels) {
            const pt = map.latLngToContainerPoint([v.latitude, v.longitude]);
            const dx = pt.x - clickPt.x;
            const dy = pt.y - clickPt.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < hitRadius && dist < closestDist) {
                closest = v;
                closestDist = dist;
            }
        }

        if (closest) {
            if (popupRef.current) map.closePopup(popupRef.current);

            const flagUrl = getFlagUrl(closest.flag);
            const photoUrl = closest.ship_id && !closest.ship_id.includes('==')
                ? `https://www.marinetraffic.com/getAssetDefaultPhoto/?photo_size=800&asset_id=${closest.ship_id}&asset_type_id=0`
                : null;

            const html = `
                <div style="font-size:12px;min-width:210px;line-height:1.5;color:#F8FAFC">
                    ${photoUrl ? `<img src="${photoUrl}" style="width:100%;height:80px;object-fit:cover;border-radius:4px;margin-bottom:6px" onerror="this.style.display='none'" />` : ''}
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                        ${flagUrl ? `<img src="${flagUrl}" style="width:24px;height:16px;object-fit:cover;border-radius:2px;border:1px solid #333" onerror="this.style.display='none'" />` : ''}
                        <strong style="font-size:13px">${closest.name || 'Unknown'}</strong>
                    </div>
                    <div style="color:#aaa">Type: <span style="color:#F8FAFC">${closest.vessel_type || 'N/A'}</span></div>
                    <div style="color:#aaa">MMSI: <span style="color:#F8FAFC">${closest.mmsi || 'N/A'}</span></div>
                    <div style="color:#aaa">Flag: <span style="color:#F8FAFC">${closest.flag || 'N/A'}</span></div>
                    <div style="color:#aaa">Speed: <span style="color:#F8FAFC">${closest.speed ?? 'N/A'} kn</span></div>
                    <div style="color:#aaa">Course: <span style="color:#F8FAFC">${closest.course ?? 'N/A'}&deg;</span></div>
                    <div style="color:#aaa">Heading: <span style="color:#F8FAFC">${closest.heading ?? 'N/A'}&deg;</span></div>
                    <div style="color:#aaa">Status: <span style="color:#F8FAFC">${closest.nav_status || 'N/A'}</span></div>
                    ${closest.destination ? `<div style="color:#aaa">Dest: <span style="color:#F8FAFC">${closest.destination}</span></div>` : ''}
                    ${closest.length ? `<div style="color:#aaa">Size: <span style="color:#F8FAFC">${closest.length}m x ${closest.width || '?'}m</span></div>` : ''}
                    ${closest.dwt ? `<div style="color:#aaa">DWT: <span style="color:#F8FAFC">${Number(closest.dwt).toLocaleString()} t</span></div>` : ''}
                </div>
            `;

            popupRef.current = L.popup({ className: 'vessel-popup' })
                .setLatLng([closest.latitude, closest.longitude])
                .setContent(html)
                .openOn(map);
        }
    }, [map, vessels]);

    useEffect(() => {
        map.on('click', handleClick);
        return () => { map.off('click', handleClick); };
    }, [map, handleClick]);

    return null;
}

function MapInit({ vessels }) {
    const map = useMap();
    useEffect(() => {
        if (!vessels || vessels.length === 0) {
            map.setView([0, 100], 3);
        }
    }, [vessels, map]);
    return null;
}

export default function VesselMap({ vessels = [], height = '400px' }) {
    return (
        <div data-testid="vessel-map" className="rounded-md overflow-hidden border border-[#1E293B]" style={{ height }}>
            <MapContainer
                center={[0, 100]}
                zoom={3}
                style={{ height: '100%', width: '100%' }}
                attributionControl={true}
            >
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
                    attribution='&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://osm.org/copyright">OSM</a>'
                    maxZoom={19}
                    subdomains="abcd"
                />
                <MapInit vessels={vessels} />
                <VesselLayer vessels={vessels} />
            </MapContainer>
        </div>
    );
}
