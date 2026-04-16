import { useEffect } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const VESSEL_COLORS = {
    'Cargo': '#10B981',
    'General Cargo': '#10B981',
    'Tanker': '#F43F5E',
    'Container Ship': '#00A6FB',
    'Bulk Carrier': '#F59E0B',
    'Passenger': '#A855F7',
    'Fishing': '#06B6D4',
    'High Speed Craft': '#EC4899',
    'Tug': '#8B5CF6',
    'Supply Vessel': '#14B8A6',
    'Special Craft': '#6366F1',
};

function getVesselColor(type) {
    return VESSEL_COLORS[type] || '#94A3B8';
}

function MapBounds({ vessels }) {
    const map = useMap();
    useEffect(() => {
        if (!vessels || vessels.length === 0) {
            map.setView([5, 115], 4);
        }
    }, [vessels, map]);
    return null;
}

export default function VesselMap({ vessels = [], height = '400px' }) {
    return (
        <div data-testid="vessel-map" className="rounded-md overflow-hidden border border-[#1E293B]" style={{ height }}>
            <MapContainer
                center={[5, 115]}
                zoom={4}
                style={{ height: '100%', width: '100%' }}
                attributionControl={true}
            >
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; <a href="https://carto.com/">CARTO</a>'
                />
                <MapBounds vessels={vessels} />
                {vessels.map((v, i) => (
                    <CircleMarker
                        key={v.mmsi || i}
                        center={[v.latitude, v.longitude]}
                        radius={4}
                        pathOptions={{
                            color: getVesselColor(v.vessel_type),
                            fillColor: getVesselColor(v.vessel_type),
                            fillOpacity: 0.8,
                            weight: 1,
                        }}
                    >
                        <Popup>
                            <div className="text-xs space-y-1">
                                <p className="font-bold text-sm">{v.name || 'Unknown'}</p>
                                <p><span className="text-gray-400">Type:</span> {v.vessel_type}</p>
                                <p><span className="text-gray-400">MMSI:</span> {v.mmsi}</p>
                                <p><span className="text-gray-400">Flag:</span> {v.flag || 'N/A'}</p>
                                <p><span className="text-gray-400">Speed:</span> {v.speed ?? 'N/A'} kn</p>
                                <p><span className="text-gray-400">Course:</span> {v.course ?? 'N/A'}&deg;</p>
                                <p><span className="text-gray-400">Status:</span> {v.nav_status || 'N/A'}</p>
                            </div>
                        </Popup>
                    </CircleMarker>
                ))}
            </MapContainer>
        </div>
    );
}
