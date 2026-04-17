import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import VesselMap from '../components/VesselMap';
import { Ship, Anchor, Activity, Clock, Wifi, WifiOff, RefreshCw, Loader2 } from 'lucide-react';

function getTypeBadge(type) {
    const map = {
        'Cargo': 'badge-cargo', 'General Cargo': 'badge-cargo',
        'Tanker': 'badge-tanker', 'Container Ship': 'badge-container',
        'Bulk Carrier': 'badge-bulk', 'Passenger': 'badge-passenger',
        'Fishing': 'badge-fishing',
    };
    return map[type] || 'badge-default';
}

export default function DashboardPage() {
    const { axiosAuth } = useAuth();
    const [stats, setStats] = useState(null);
    const [vessels, setVessels] = useState([]);
    const [botStatus, setBotStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [extracting, setExtracting] = useState(false);

    const fetchData = useCallback(async () => {
        try {
            const api = axiosAuth();
            const [statsRes, mapRes, botRes] = await Promise.all([
                api.get('/vessels/stats'),
                api.get('/vessels/map'),
                api.get('/bot/status'),
            ]);
            setStats(statsRes.data);
            setVessels(mapRes.data.vessels || []);
            setBotStatus(botRes.data);
        } catch (err) {
            console.error('Dashboard fetch error:', err);
        }
        setLoading(false);
    }, [axiosAuth]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleExtractNow = async () => {
        setExtracting(true);
        try {
            const api = axiosAuth();
            await api.post('/bot/extract-now');
            await fetchData();
        } catch (err) {
            console.error('Extract error:', err);
        }
        setExtracting(false);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" />
            </div>
        );
    }

    const statCards = [
        { label: 'Total Vessels', value: stats?.total_vessels || 0, icon: Ship, color: '#00A6FB' },
        { label: 'Avg Speed', value: `${stats?.avg_speed || 0} kn`, icon: Activity, color: '#10B981' },
        { label: 'Extractions', value: stats?.total_extractions || 0, icon: Clock, color: '#F59E0B' },
        { label: 'Bot Status', value: botStatus?.running ? 'Active' : 'Stopped', icon: botStatus?.running ? Wifi : WifiOff, color: botStatus?.running ? '#10B981' : '#F43F5E' },
    ];

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-6" data-testid="dashboard-page">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-[#F8FAFC] tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                        Dashboard
                    </h1>
                    <p className="text-sm text-[#10B981] mt-1 flex items-center gap-1.5">
                        <span className="w-2 h-2 bg-[#10B981] rounded-full animate-pulse" />
                        Live Data dari MarineTraffic - ASEAN, Australia, Indian Ocean, Red Sea
                    </p>
                </div>
                <button
                    data-testid="extract-now-button"
                    onClick={handleExtractNow}
                    disabled={extracting}
                    className="flex items-center gap-2 bg-[#00A6FB] hover:bg-[#008CD4] active:scale-[0.98] text-white text-sm font-medium px-4 py-2 rounded-md transition-all duration-200 disabled:opacity-60"
                >
                    {extracting ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                    {extracting ? 'Extracting...' : 'Extract Now'}
                </button>
            </div>

            {/* Stat Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {statCards.map((card, i) => (
                    <div key={i} className="stat-card animate-fade-up" style={{ animationDelay: `${i * 80}ms` }} data-testid={`stat-card-${i}`}>
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-xs text-[#64748B] uppercase tracking-[0.15em] font-medium">{card.label}</span>
                            <card.icon className="w-4 h-4" style={{ color: card.color }} />
                        </div>
                        <p className="text-2xl font-bold text-[#F8FAFC]" style={{ fontFamily: 'Chivo, sans-serif', color: card.color }}>
                            {card.value}
                        </p>
                    </div>
                ))}
            </div>

            {/* Map */}
            <div className="animate-fade-up" style={{ animationDelay: '320ms' }}>
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-lg font-bold text-[#F8FAFC]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                        Live Vessel Map
                    </h2>
                    <span className="text-xs text-[#64748B] font-mono">
                        {vessels.length} vessels plotted
                    </span>
                </div>
                <VesselMap vessels={vessels} height="450px" />
            </div>

            {/* Vessel Type & Recent Table */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-fade-up" style={{ animationDelay: '400ms' }}>
                {/* Vessel Types */}
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-5">
                    <h3 className="text-sm font-bold text-[#F8FAFC] mb-4 uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                        Vessel Types
                    </h3>
                    <div className="space-y-3">
                        {(stats?.vessel_types || []).slice(0, 8).map((t, i) => (
                            <div key={i} className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${getTypeBadge(t.type)}`}>
                                        {t.type}
                                    </span>
                                </div>
                                <span className="text-sm font-mono text-[#F8FAFC]">{t.count}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recent Vessels Table */}
                <div className="lg:col-span-2 bg-[#0F1621] border border-[#1E293B] rounded-md overflow-hidden">
                    <div className="p-4 border-b border-[#1E293B]">
                        <h3 className="text-sm font-bold text-[#F8FAFC] uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                            Recent Vessels
                        </h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Type</th>
                                    <th>Flag</th>
                                    <th>Speed</th>
                                    <th>Position</th>
                                </tr>
                            </thead>
                            <tbody>
                                {vessels.slice(0, 10).map((v, i) => (
                                    <tr key={v.mmsi || i}>
                                        <td className="font-medium">{v.name || 'N/A'}</td>
                                        <td>
                                            <span className={`inline-block px-2 py-0.5 rounded text-xs ${getTypeBadge(v.vessel_type)}`}>
                                                {v.vessel_type}
                                            </span>
                                        </td>
                                        <td className="text-[#94A3B8]">{v.flag || 'N/A'}</td>
                                        <td className="font-mono">{v.speed ?? 'N/A'} kn</td>
                                        <td className="font-mono text-xs text-[#94A3B8]">
                                            {v.latitude?.toFixed(4)}, {v.longitude?.toFixed(4)}
                                        </td>
                                    </tr>
                                ))}
                                {vessels.length === 0 && (
                                    <tr>
                                        <td colSpan="5" className="text-center text-[#64748B] py-8">
                                            No vessel data. Click "Extract Now" to start.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {/* Last Extraction Info */}
            {stats?.last_extraction && (
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-4 flex items-center gap-4 text-sm animate-fade-up" style={{ animationDelay: '480ms' }}>
                    <Anchor className="w-4 h-4 text-[#00A6FB]" />
                    <span className="text-[#94A3B8]">Last extraction:</span>
                    <span className="font-mono text-[#F8FAFC]">{new Date(stats.last_extraction.timestamp).toLocaleString()}</span>
                    <span className="text-[#64748B]">&middot;</span>
                    <span className="text-[#10B981]">{stats.last_extraction.vessels_count} vessels</span>
                    <span className="text-[#64748B]">&middot;</span>
                    <span className="text-[#94A3B8]">{stats.last_extraction.source}</span>
                    <span className="text-[#64748B]">&middot;</span>
                    <span className="font-mono text-[#94A3B8]">{stats.last_extraction.duration_seconds}s</span>
                </div>
            )}
        </div>
    );
}
