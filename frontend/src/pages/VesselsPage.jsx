import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { Search, Download, ChevronLeft, ChevronRight, Filter, Loader2, Ship } from 'lucide-react';

function getTypeBadge(type) {
    const map = {
        'Cargo': 'badge-cargo', 'General Cargo': 'badge-cargo',
        'Tanker': 'badge-tanker', 'Container Ship': 'badge-container',
        'Bulk Carrier': 'badge-bulk', 'Passenger': 'badge-passenger',
        'Fishing': 'badge-fishing',
    };
    return map[type] || 'badge-default';
}

export default function VesselsPage() {
    const { axiosAuth } = useAuth();
    const [vessels, setVessels] = useState([]);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(0);
    const [page, setPage] = useState(1);
    const [search, setSearch] = useState('');
    const [vesselType, setVesselType] = useState('');
    const [flag, setFlag] = useState('');
    const [types, setTypes] = useState([]);
    const [flags, setFlags] = useState([]);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);

    const fetchVessels = useCallback(async () => {
        setLoading(true);
        try {
            const api = axiosAuth();
            const params = { page, limit: 50 };
            if (search) params.search = search;
            if (vesselType) params.vessel_type = vesselType;
            if (flag) params.flag = flag;
            const res = await api.get('/vessels', { params });
            setVessels(res.data.vessels || []);
            setTotal(res.data.total || 0);
            setPages(res.data.pages || 0);
        } catch (err) {
            console.error('Fetch vessels error:', err);
        }
        setLoading(false);
    }, [axiosAuth, page, search, vesselType, flag]);

    const fetchFilters = useCallback(async () => {
        try {
            const api = axiosAuth();
            const [typesRes, flagsRes] = await Promise.all([
                api.get('/vessels/types'),
                api.get('/vessels/flags'),
            ]);
            setTypes(typesRes.data.types || []);
            setFlags(flagsRes.data.flags || []);
        } catch (err) {
            console.error('Fetch filters error:', err);
        }
    }, [axiosAuth]);

    useEffect(() => { fetchFilters(); }, [fetchFilters]);
    useEffect(() => { fetchVessels(); }, [fetchVessels]);

    const handleExport = async () => {
        setExporting(true);
        try {
            const api = axiosAuth();
            const res = await api.get('/vessels/export/csv', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `ais_data_${new Date().toISOString().slice(0,10)}.csv`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Export error:', err);
        }
        setExporting(false);
    };

    const handleSearch = (e) => {
        e.preventDefault();
        setPage(1);
        fetchVessels();
    };

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-6" data-testid="vessels-page">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-[#F8FAFC] tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                        Vessel Data
                    </h1>
                    <p className="text-sm text-[#94A3B8] mt-1">
                        {total} vessels in ASEAN region
                    </p>
                </div>
                <button
                    data-testid="export-csv-button"
                    onClick={handleExport}
                    disabled={exporting || total === 0}
                    className="flex items-center gap-2 bg-[#10B981] hover:bg-[#059669] active:scale-[0.98] text-white text-sm font-medium px-4 py-2 rounded-md transition-all duration-200 disabled:opacity-60"
                >
                    {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    Export CSV
                </button>
            </div>

            {/* Filters */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-4">
                <div className="flex flex-wrap items-end gap-3">
                    <form onSubmit={handleSearch} className="flex-1 min-w-[200px]">
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] mb-1.5 block">Search</label>
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748B]" />
                            <input
                                data-testid="vessel-search-input"
                                type="text"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Name, MMSI, or IMO..."
                                className="w-full bg-[#050A10] border border-[#1E293B] rounded-md pl-10 pr-4 py-2 text-sm text-[#F8FAFC] placeholder-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00A6FB] focus:border-transparent"
                            />
                        </div>
                    </form>
                    <div className="min-w-[160px]">
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] mb-1.5 block">Vessel Type</label>
                        <select
                            data-testid="vessel-type-filter"
                            value={vesselType}
                            onChange={(e) => { setVesselType(e.target.value); setPage(1); }}
                            className="w-full bg-[#050A10] border border-[#1E293B] rounded-md px-3 py-2 text-sm text-[#F8FAFC] focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                        >
                            <option value="">All Types</option>
                            {types.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                    </div>
                    <div className="min-w-[120px]">
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] mb-1.5 block">Flag</label>
                        <select
                            data-testid="vessel-flag-filter"
                            value={flag}
                            onChange={(e) => { setFlag(e.target.value); setPage(1); }}
                            className="w-full bg-[#050A10] border border-[#1E293B] rounded-md px-3 py-2 text-sm text-[#F8FAFC] focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                        >
                            <option value="">All Flags</option>
                            {flags.map(f => <option key={f} value={f}>{f}</option>)}
                        </select>
                    </div>
                    <button
                        data-testid="clear-filters-button"
                        onClick={() => { setSearch(''); setVesselType(''); setFlag(''); setPage(1); }}
                        className="flex items-center gap-1 text-sm text-[#94A3B8] hover:text-[#F8FAFC] px-3 py-2 rounded-md hover:bg-[#172233] transition-colors"
                    >
                        <Filter className="w-3.5 h-3.5" />
                        Clear
                    </button>
                </div>
            </div>

            {/* Table */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md overflow-hidden">
                {loading ? (
                    <div className="flex items-center justify-center py-16">
                        <Loader2 className="w-6 h-6 text-[#00A6FB] animate-spin" />
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table" data-testid="vessels-table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>MMSI</th>
                                    <th>IMO</th>
                                    <th>Type</th>
                                    <th>Flag</th>
                                    <th>Lat</th>
                                    <th>Lon</th>
                                    <th>Speed</th>
                                    <th>Course</th>
                                    <th>Status</th>
                                    <th>Destination</th>
                                </tr>
                            </thead>
                            <tbody>
                                {vessels.map((v, i) => (
                                    <tr key={v.mmsi || i} data-testid={`vessel-row-${i}`}>
                                        <td className="font-medium whitespace-nowrap">
                                            <div className="flex items-center gap-2">
                                                {v.ship_id && !v.ship_id.includes('==') && (
                                                    <img
                                                        src={`https://photos.marinetraffic.com/ais/showphoto.aspx?shipid=${v.ship_id}&size=thumb300`}
                                                        alt=""
                                                        className="w-8 h-8 rounded object-cover flex-shrink-0"
                                                        onError={(e) => { e.target.style.display = 'none'; }}
                                                    />
                                                )}
                                                <span>{v.name || 'N/A'}</span>
                                            </div>
                                        </td>
                                        <td className="font-mono text-xs">{v.mmsi}</td>
                                        <td className="font-mono text-xs text-[#94A3B8]">{v.imo || '-'}</td>
                                        <td>
                                            <span className={`inline-block px-2 py-0.5 rounded text-xs whitespace-nowrap ${getTypeBadge(v.vessel_type)}`}>
                                                {v.vessel_type}
                                            </span>
                                        </td>
                                        <td className="text-[#94A3B8]">{v.flag || '-'}</td>
                                        <td className="font-mono text-xs">{v.latitude?.toFixed(4)}</td>
                                        <td className="font-mono text-xs">{v.longitude?.toFixed(4)}</td>
                                        <td className="font-mono">{v.speed ?? '-'}</td>
                                        <td className="font-mono text-xs">{v.course ?? '-'}&deg;</td>
                                        <td className="text-xs text-[#94A3B8] whitespace-nowrap">{v.nav_status || '-'}</td>
                                        <td className="text-xs text-[#94A3B8]">{v.destination || '-'}</td>
                                    </tr>
                                ))}
                                {vessels.length === 0 && (
                                    <tr>
                                        <td colSpan="11" className="text-center text-[#64748B] py-12">
                                            <Ship className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                            No vessels found
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Pagination */}
                {pages > 1 && (
                    <div className="flex items-center justify-between px-4 py-3 border-t border-[#1E293B]">
                        <span className="text-xs text-[#64748B]">
                            Page {page} of {pages} &middot; {total} vessels
                        </span>
                        <div className="flex gap-1">
                            <button
                                data-testid="prev-page-button"
                                onClick={() => setPage(p => Math.max(1, p - 1))}
                                disabled={page <= 1}
                                className="p-1.5 rounded-md text-[#94A3B8] hover:bg-[#172233] disabled:opacity-30 transition-colors"
                            >
                                <ChevronLeft className="w-4 h-4" />
                            </button>
                            <button
                                data-testid="next-page-button"
                                onClick={() => setPage(p => Math.min(pages, p + 1))}
                                disabled={page >= pages}
                                className="p-1.5 rounded-md text-[#94A3B8] hover:bg-[#172233] disabled:opacity-30 transition-colors"
                            >
                                <ChevronRight className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
