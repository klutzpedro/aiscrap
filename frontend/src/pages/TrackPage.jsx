import { useEffect, useState, useCallback, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import { useParams, useNavigate } from 'react-router-dom';
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Search, Loader2, Clock, Navigation, Anchor, MapPin, Ship } from 'lucide-react';

function FitBounds({ track }) {
    const map = useMap();
    useEffect(() => {
        if (track && track.length > 1) {
            const bounds = L.latLngBounds(track.map(p => [p.latitude, p.longitude]));
            map.fitBounds(bounds, { padding: [40, 40] });
        } else if (track && track.length === 1) {
            map.setView([track[0].latitude, track[0].longitude], 10);
        }
    }, [track, map]);
    return null;
}

export default function TrackPage() {
    const { axiosAuth } = useAuth();
    const { shipId: paramShipId } = useParams();
    const navigate = useNavigate();
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [selectedShip, setSelectedShip] = useState(null);
    const [trackData, setTrackData] = useState(null);
    const [hours, setHours] = useState(168);
    const [loading, setLoading] = useState(false);
    const [searchLoading, setSearchLoading] = useState(false);

    // Load track if shipId in URL
    useEffect(() => {
        if (paramShipId) loadTrack(paramShipId);
    }, [paramShipId]);

    const searchVessels = async (e) => {
        e.preventDefault();
        if (!searchQuery.trim()) return;
        setSearchLoading(true);
        try {
            const api = axiosAuth();
            const res = await api.get('/vessels', { params: { search: searchQuery, limit: 20 } });
            setSearchResults(res.data.vessels || []);
        } catch (err) {
            console.error('Search error:', err);
        }
        setSearchLoading(false);
    };

    const loadTrack = useCallback(async (shipId, h) => {
        setLoading(true);
        try {
            const api = axiosAuth();
            const res = await api.get(`/vessels/${shipId}/track`, { params: { hours: h || hours } });
            setTrackData(res.data);
            setSelectedShip(res.data.vessel);
            if (!paramShipId || paramShipId !== shipId) {
                navigate(`/track/${shipId}`, { replace: true });
            }
        } catch (err) {
            console.error('Track error:', err);
        }
        setLoading(false);
    }, [axiosAuth, hours, navigate, paramShipId]);

    const selectVessel = (vessel) => {
        setSearchResults([]);
        setSearchQuery(vessel.name || '');
        loadTrack(vessel.ship_id);
    };

    const trackPoints = useMemo(() => {
        if (!trackData?.track) return [];
        return trackData.track.map(p => [p.latitude, p.longitude]);
    }, [trackData]);

    const flagUrl = selectedShip?.flag
        ? `https://flagcdn.com/w40/${selectedShip.flag.toLowerCase()}.png` : null;

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-5" data-testid="track-page">
            {/* Header */}
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-[#F8FAFC] tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    Vessel Track
                </h1>
                <p className="text-sm text-[#94A3B8] mt-1">
                    Lacak pergerakan kapal berdasarkan history extraction
                </p>
            </div>

            {/* Search & Controls */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-4">
                <div className="flex flex-wrap items-end gap-3">
                    <form onSubmit={searchVessels} className="flex-1 min-w-[250px]">
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] mb-1.5 block">Cari Kapal</label>
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748B]" />
                            <input
                                data-testid="track-search-input"
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Nama kapal, MMSI, atau IMO..."
                                className="w-full bg-[#050A10] border border-[#1E293B] rounded-md pl-10 pr-4 py-2 text-sm text-[#F8FAFC] placeholder-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                            />
                        </div>
                    </form>
                    <div>
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] mb-1.5 block">Rentang Waktu</label>
                        <select
                            data-testid="track-hours-select"
                            value={hours}
                            onChange={(e) => {
                                const h = Number(e.target.value);
                                setHours(h);
                                if (selectedShip?.ship_id) loadTrack(selectedShip.ship_id, h);
                            }}
                            className="bg-[#050A10] border border-[#1E293B] rounded-md px-3 py-2 text-sm text-[#F8FAFC] focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                        >
                            <option value={6}>6 Jam</option>
                            <option value={12}>12 Jam</option>
                            <option value={24}>24 Jam</option>
                            <option value={48}>2 Hari</option>
                            <option value={72}>3 Hari</option>
                            <option value={168}>7 Hari</option>
                            <option value={336}>14 Hari</option>
                            <option value={720}>30 Hari</option>
                        </select>
                    </div>
                    <button
                        data-testid="track-search-button"
                        onClick={searchVessels}
                        disabled={searchLoading}
                        className="flex items-center gap-2 bg-[#00A6FB] hover:bg-[#008CD4] text-white text-sm font-medium px-4 py-2 rounded-md transition-all duration-200"
                    >
                        {searchLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                        Cari
                    </button>
                </div>

                {/* Search Results */}
                {searchResults.length > 0 && (
                    <div className="mt-3 border border-[#1E293B] rounded-md overflow-hidden max-h-[200px] overflow-y-auto">
                        {searchResults.map((v, i) => (
                            <button
                                key={v.ship_id || v.mmsi || i}
                                onClick={() => selectVessel(v)}
                                data-testid={`search-result-${i}`}
                                className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm hover:bg-[#172233] border-b border-[#1E293B] last:border-0 transition-colors"
                            >
                                {v.flag && (
                                    <img
                                        src={`https://flagcdn.com/w20/${v.flag.toLowerCase()}.png`}
                                        alt={v.flag}
                                        className="w-5 h-3.5 object-cover rounded-sm"
                                        onError={(e) => { e.target.style.display = 'none'; }}
                                    />
                                )}
                                <span className="text-[#F8FAFC] font-medium">{v.name}</span>
                                <span className="text-xs text-[#64748B]">{v.vessel_type}</span>
                                <span className="text-xs font-mono text-[#94A3B8] ml-auto">{v.mmsi}</span>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Vessel Info Card */}
            {selectedShip && (
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-4 flex flex-wrap items-center gap-4">
                    {selectedShip.photo_url && (
                        <img
                            src={selectedShip.photo_url}
                            alt={selectedShip.name}
                            className="w-20 h-14 object-cover rounded"
                            onError={(e) => { e.target.style.display = 'none'; }}
                        />
                    )}
                    <div className="flex items-center gap-2">
                        {flagUrl && (
                            <img src={flagUrl} alt={selectedShip.flag} className="w-6 h-4 object-cover rounded-sm border border-[#333]"
                                onError={(e) => { e.target.style.display = 'none'; }} />
                        )}
                        <h2 className="text-lg font-bold text-[#F8FAFC]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                            {selectedShip.name}
                        </h2>
                    </div>
                    <div className="flex flex-wrap gap-4 text-xs text-[#94A3B8]">
                        <span><Ship className="w-3 h-3 inline mr-1" />{selectedShip.vessel_type}</span>
                        <span>MMSI: <span className="font-mono text-[#F8FAFC]">{selectedShip.mmsi}</span></span>
                        {selectedShip.destination && <span><MapPin className="w-3 h-3 inline mr-1" />{selectedShip.destination}</span>}
                        {selectedShip.speed !== undefined && <span><Navigation className="w-3 h-3 inline mr-1" />{selectedShip.speed} kn</span>}
                        {selectedShip.length && <span>{selectedShip.length}m x {selectedShip.width || '?'}m</span>}
                    </div>
                    {trackData && (
                        <div className="ml-auto text-right">
                            <span className="text-sm font-mono text-[#00A6FB]">{trackData.track_points} titik track</span>
                            <p className="text-xs text-[#64748B]">{hours} jam terakhir</p>
                        </div>
                    )}
                </div>
            )}

            {/* Track Map */}
            <div className="rounded-md overflow-hidden border border-[#1E293B]" style={{ height: '500px' }}>
                {loading ? (
                    <div className="flex items-center justify-center h-full bg-[#050A10]">
                        <Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" />
                    </div>
                ) : (
                    <MapContainer center={[0, 100]} zoom={3} style={{ height: '100%', width: '100%' }}>
                        <TileLayer
                            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
                            attribution='&copy; CARTO &copy; OSM'
                            maxZoom={19}
                            subdomains="abcd"
                        />
                        {trackData?.track && <FitBounds track={trackData.track} />}

                        {/* Track line */}
                        {trackPoints.length > 1 && (
                            <Polyline
                                positions={trackPoints}
                                pathOptions={{ color: '#00A6FB', weight: 2.5, opacity: 0.8, dashArray: '6 4' }}
                            />
                        )}

                        {/* Track points */}
                        {trackData?.track?.map((p, i) => {
                            const isFirst = i === 0;
                            const isLast = i === (trackData.track.length - 1);
                            const color = isLast ? '#10B981' : isFirst ? '#F59E0B' : '#00A6FB';
                            const radius = isFirst || isLast ? 6 : 3;

                            return (
                                <CircleMarker
                                    key={i}
                                    center={[p.latitude, p.longitude]}
                                    radius={radius}
                                    pathOptions={{ color, fillColor: color, fillOpacity: 0.9, weight: isFirst || isLast ? 2 : 0.5 }}
                                >
                                    <Popup>
                                        <div style={{ fontSize: '11px', lineHeight: '1.6', color: '#F8FAFC' }}>
                                            <strong>{isFirst ? 'START' : isLast ? 'CURRENT' : `Point ${i + 1}`}</strong>
                                            <br />
                                            <span style={{ color: '#aaa' }}>Time:</span> {new Date(p.recorded_at).toLocaleString()}
                                            <br />
                                            <span style={{ color: '#aaa' }}>Pos:</span> {p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}
                                            <br />
                                            <span style={{ color: '#aaa' }}>Speed:</span> {p.speed} kn
                                            <br />
                                            <span style={{ color: '#aaa' }}>Course:</span> {p.course}&deg;
                                            {p.nav_status && <><br /><span style={{ color: '#aaa' }}>Status:</span> {p.nav_status}</>}
                                        </div>
                                    </Popup>
                                </CircleMarker>
                            );
                        })}

                        {/* No data message */}
                        {!trackData && !loading && (
                            <div className="absolute inset-0 z-[1000] flex items-center justify-center pointer-events-none">
                                <div className="bg-[#0F1621]/90 text-[#94A3B8] text-sm rounded-md px-6 py-4 text-center">
                                    <Anchor className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                    <p>Cari nama kapal untuk melihat track pergerakan</p>
                                </div>
                            </div>
                        )}
                    </MapContainer>
                )}
            </div>

            {/* Track Timeline */}
            {trackData?.track && trackData.track.length > 0 && (
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md overflow-hidden">
                    <div className="p-4 border-b border-[#1E293B] flex items-center justify-between">
                        <h3 className="text-sm font-bold text-[#F8FAFC] uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                            <Clock className="w-4 h-4 inline mr-2" />
                            Track Timeline
                        </h3>
                        <span className="text-xs text-[#64748B]">{trackData.track.length} data points</span>
                    </div>
                    <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Waktu</th>
                                    <th>Latitude</th>
                                    <th>Longitude</th>
                                    <th>Speed</th>
                                    <th>Course</th>
                                    <th>Heading</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trackData.track.map((p, i) => (
                                    <tr key={i}>
                                        <td className="font-mono text-xs text-[#64748B]">{i + 1}</td>
                                        <td className="font-mono text-xs whitespace-nowrap">{new Date(p.recorded_at).toLocaleString()}</td>
                                        <td className="font-mono text-xs">{p.latitude?.toFixed(5)}</td>
                                        <td className="font-mono text-xs">{p.longitude?.toFixed(5)}</td>
                                        <td className="font-mono">{p.speed} kn</td>
                                        <td className="font-mono text-xs">{p.course}&deg;</td>
                                        <td className="font-mono text-xs">{p.heading}&deg;</td>
                                        <td className="text-xs text-[#94A3B8]">{p.nav_status || '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
