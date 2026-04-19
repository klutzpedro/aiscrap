import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { Shield, AlertTriangle, MapPin, Loader2, RefreshCw, Zap, FileText, ChevronDown, ChevronUp } from 'lucide-react';

const SEV_COLORS = {
    CRITICAL: 'bg-[#F43F5E]/15 text-[#F43F5E] border-[#F43F5E]/30',
    HIGH: 'bg-[#F59E0B]/15 text-[#F59E0B] border-[#F59E0B]/30',
    MEDIUM: 'bg-[#00A6FB]/15 text-[#00A6FB] border-[#00A6FB]/30',
};

const TYPE_LABELS = {
    ZONE_INTRUSION: 'Zone Intrusion',
    SPEED_ANOMALY: 'Speed Anomaly',
    AIS_GAP: 'AIS Gap (Dark Vessel)',
    LOITERING: 'Loitering',
    POSITION_JUMP: 'Position Jump (Spoofing)',
};

export default function AnalyticsPage() {
    const { axiosAuth } = useAuth();
    const [analysis, setAnalysis] = useState(null);
    const [aiReport, setAiReport] = useState(null);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [generatingAI, setGeneratingAI] = useState(false);
    const [expandedZone, setExpandedZone] = useState(null);
    const [sevFilter, setSevFilter] = useState('');

    const fetchData = useCallback(async () => {
        try {
            const api = axiosAuth();
            const [analysisRes, aiRes] = await Promise.all([
                api.get('/ext/analytics/latest').catch(() => ({ data: null })),
                api.get('/ext/analytics/ai-report').catch(() => ({ data: null })),
            ]);
            if (analysisRes.data && !analysisRes.data.message) setAnalysis(analysisRes.data);
            if (aiRes.data && !aiRes.data.message) setAiReport(aiRes.data);
        } catch (err) { console.error(err); }
        setLoading(false);
    }, [axiosAuth]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const runAnalysis = async () => {
        setAnalyzing(true);
        try {
            const api = axiosAuth();
            const res = await api.post('/ext/analytics/run');
            setAnalysis(res.data);
        } catch (err) { console.error(err); }
        setAnalyzing(false);
    };

    const generateAIReport = async () => {
        setGeneratingAI(true);
        try {
            const api = axiosAuth();
            const res = await api.post('/ext/analytics/ai-report');
            setAiReport(res.data);
        } catch (err) { console.error(err); }
        setGeneratingAI(false);
    };

    const s = analysis?.summary || {};
    const zones = analysis?.zone_reports || {};
    const anomalies = (analysis?.anomalies || []).filter(a => !sevFilter || a.severity === sevFilter);

    if (loading) return <div className="flex items-center justify-center min-h-screen"><Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" /></div>;

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-5" data-testid="analytics-page">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold text-[#F8FAFC] tracking-tight flex items-center gap-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
                        <Shield className="w-7 h-7 text-[#F43F5E]" />
                        Maritime Intelligence
                    </h1>
                    <p className="text-sm text-[#94A3B8] mt-1">Anomaly Detection & Threat Assessment - TNI AL</p>
                </div>
                <div className="flex gap-2">
                    <button data-testid="run-analysis-btn" onClick={runAnalysis} disabled={analyzing}
                        className="flex items-center gap-2 bg-[#F43F5E] hover:bg-[#E11D48] text-white text-sm font-medium px-4 py-2 rounded-md transition-all disabled:opacity-60">
                        {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                        Run Analysis
                    </button>
                    <button data-testid="ai-report-btn" onClick={generateAIReport} disabled={generatingAI || !analysis}
                        className="flex items-center gap-2 bg-[#00A6FB] hover:bg-[#008CD4] text-white text-sm font-medium px-4 py-2 rounded-md transition-all disabled:opacity-60">
                        {generatingAI ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                        AI SITREP
                    </button>
                </div>
            </div>

            {!analysis ? (
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-12 text-center">
                    <Shield className="w-12 h-12 text-[#64748B] mx-auto mb-3" />
                    <p className="text-[#94A3B8]">Belum ada data analisis. Klik <strong>Run Analysis</strong> untuk mulai.</p>
                </div>
            ) : (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        {[
                            { label: 'Total Anomali', value: s.total_anomalies, color: '#F43F5E' },
                            { label: 'CRITICAL', value: s.critical, color: '#F43F5E' },
                            { label: 'HIGH', value: s.high, color: '#F59E0B' },
                            { label: 'Zone Intrusion', value: s.zone_intrusions, color: '#A855F7' },
                            { label: 'AIS Gap', value: s.ais_gaps, color: '#06B6D4' },
                            { label: 'Loitering', value: s.loitering_detected, color: '#10B981' },
                        ].map((c, i) => (
                            <div key={i} className="stat-card animate-fade-up" style={{ animationDelay: `${i * 60}ms` }}>
                                <span className="text-[10px] text-[#64748B] uppercase tracking-[0.15em]">{c.label}</span>
                                <p className="text-2xl font-bold mt-1" style={{ color: c.color, fontFamily: 'Chivo, sans-serif' }}>{c.value || 0}</p>
                            </div>
                        ))}
                    </div>

                    {/* Zone Reports */}
                    <div className="space-y-2">
                        <h2 className="text-sm font-bold text-[#F8FAFC] uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                            <MapPin className="w-4 h-4 inline mr-2 text-[#F43F5E]" />Zona Strategis
                        </h2>
                        {Object.entries(zones).map(([zid, z]) => z && (
                            <div key={zid} className="bg-[#0F1621] border border-[#1E293B] rounded-md overflow-hidden">
                                <button
                                    onClick={() => setExpandedZone(expandedZone === zid ? null : zid)}
                                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#172233] transition-colors text-left"
                                >
                                    <div className="flex items-center gap-3">
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${z.priority === 'CRITICAL' ? 'bg-[#F43F5E]/15 text-[#F43F5E]' : 'bg-[#F59E0B]/15 text-[#F59E0B]'}`}>{z.priority}</span>
                                        <span className="text-sm font-medium text-[#F8FAFC]">{z.zone_name}</span>
                                    </div>
                                    <div className="flex items-center gap-4 text-xs">
                                        <span className="text-[#F8FAFC] font-mono">{z.total_vessels} kapal</span>
                                        <span className="text-[#F43F5E]">{z.foreign_vessels} asing</span>
                                        <span className="text-[#10B981]">{z.indonesian_vessels} ID</span>
                                        {expandedZone === zid ? <ChevronUp className="w-4 h-4 text-[#64748B]" /> : <ChevronDown className="w-4 h-4 text-[#64748B]" />}
                                    </div>
                                </button>
                                {expandedZone === zid && (
                                    <div className="px-4 pb-3 border-t border-[#1E293B] pt-3 space-y-3">
                                        <div className="flex flex-wrap gap-2">
                                            {Object.entries(z.flag_distribution || {}).slice(0, 10).map(([f, c]) => (
                                                <span key={f} className="text-xs bg-[#050A10] px-2 py-1 rounded font-mono">
                                                    {f !== 'N/A' && f && <img src={`https://flagcdn.com/w20/${f.toLowerCase()}.png`} alt="" className="w-4 h-3 inline mr-1 rounded-sm" onError={e => e.target.style.display = 'none'} />}
                                                    {f}: {c}
                                                </span>
                                            ))}
                                        </div>
                                        {z.foreign_vessel_list && z.foreign_vessel_list.length > 0 && (
                                            <div className="max-h-[150px] overflow-y-auto">
                                                <table className="data-table text-xs">
                                                    <thead><tr><th>Nama</th><th>Flag</th><th>Type</th><th>Speed</th><th>Pos</th></tr></thead>
                                                    <tbody>
                                                        {z.foreign_vessel_list.slice(0, 15).map((fv, i) => (
                                                            <tr key={i}>
                                                                <td className="font-medium">{fv.name}</td>
                                                                <td>{fv.flag}</td>
                                                                <td className="text-[#94A3B8]">{fv.type}</td>
                                                                <td className="font-mono">{fv.speed} kn</td>
                                                                <td className="font-mono text-[#64748B]">{fv.lat?.toFixed(3)}, {fv.lon?.toFixed(3)}</td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Anomalies */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-bold text-[#F8FAFC] uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                                <AlertTriangle className="w-4 h-4 inline mr-2 text-[#F59E0B]" />Anomali Terdeteksi ({anomalies.length})
                            </h2>
                            <div className="flex gap-1">
                                {['', 'CRITICAL', 'HIGH', 'MEDIUM'].map(sev => (
                                    <button key={sev} onClick={() => setSevFilter(sev)}
                                        className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${sevFilter === sev ? 'bg-[#00A6FB] text-white' : 'text-[#94A3B8] hover:text-[#F8FAFC]'}`}>
                                        {sev || 'ALL'}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="max-h-[400px] overflow-y-auto space-y-1.5">
                            {anomalies.slice(0, 50).map((a, i) => (
                                <div key={i} className={`border rounded-md px-3 py-2 text-xs ${SEV_COLORS[a.severity] || 'bg-[#050A10] text-[#94A3B8]'}`}>
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-bold">[{a.severity}]</span>
                                        <span className="font-medium">{TYPE_LABELS[a.type] || a.type}</span>
                                        {a.vessel && <span className="text-[#F8FAFC]">{a.vessel.name} [{a.vessel.flag}]</span>}
                                        {a.zone_name && <span className="text-[#A855F7]">{a.zone_name}</span>}
                                    </div>
                                    <p className="mt-1 opacity-80">{a.detail}</p>
                                </div>
                            ))}
                            {anomalies.length === 0 && (
                                <p className="text-center text-[#64748B] py-8">Tidak ada anomali terdeteksi</p>
                            )}
                        </div>
                    </div>

                    {/* AI Report */}
                    {aiReport && aiReport.report && (
                        <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-5 space-y-3">
                            <div className="flex items-center justify-between">
                                <h2 className="text-sm font-bold text-[#F8FAFC] uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                                    <FileText className="w-4 h-4 inline mr-2 text-[#00A6FB]" />AI SITREP Report
                                </h2>
                                <span className="text-[10px] text-[#64748B] font-mono">{new Date(aiReport.timestamp).toLocaleString()} | {aiReport.model}</span>
                            </div>
                            <div className="bg-[#050A10] rounded-md p-4 text-sm text-[#F8FAFC] leading-relaxed whitespace-pre-wrap max-h-[500px] overflow-y-auto font-mono text-xs">
                                {aiReport.report}
                            </div>
                        </div>
                    )}

                    <p className="text-[10px] text-[#64748B] text-right">
                        Analysis: {analysis.timestamp ? new Date(analysis.timestamp).toLocaleString() : '-'}
                    </p>
                </>
            )}
        </div>
    );
}
