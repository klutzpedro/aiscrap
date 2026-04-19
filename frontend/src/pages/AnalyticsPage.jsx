import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Shield, AlertTriangle, MapPin, Loader2, Zap, FileText, ChevronDown, ChevronUp, ExternalLink, Clock, Info, X } from 'lucide-react';

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

const TYPE_EXPLANATIONS = {
    ZONE_INTRUSION: {
        title: 'Zone Intrusion (Intrusi Zona)',
        desc: 'Kapal berbendera asing terdeteksi memasuki zona perairan strategis Indonesia. Kapal ini bukan berbendera Indonesia dan berada di dalam bounding box zona yang dimonitor.',
        why_critical: 'CRITICAL jika di Laut Natuna (zona sengketa) dan bukan dari negara tetangga (SG/MY). HIGH untuk zona strategis lainnya.',
        action: 'Verifikasi tujuan kapal, cek manifest, hubungi VTS terdekat.',
    },
    SPEED_ANOMALY: {
        title: 'Speed Anomaly (Anomali Kecepatan)',
        desc: 'Kecepatan kapal melebihi batas normal untuk tipe kapalnya. Contoh: Cargo ship seharusnya maks 18 kn tapi tercatat 25 kn.',
        why_critical: 'HIGH jika melebihi 130% batas normal. MEDIUM jika sedikit di atas batas.',
        action: 'Kemungkinan: data AIS error, kapal darurat, atau kapal mencurigakan.',
    },
    AIS_GAP: {
        title: 'AIS Gap / Dark Vessel',
        desc: 'Kapal menghilang dari radar AIS selama lebih dari 2 jam lalu muncul kembali di posisi berbeda. Indikasi kapal sengaja mematikan transponder AIS.',
        why_critical: 'HIGH jika gap > 6 jam. MEDIUM jika 2-6 jam. Perpindahan posisi juga dihitung.',
        action: 'Kemungkinan: transfer kargo ilegal, menghindari monitoring, atau masuk zona terlarang.',
    },
    LOITERING: {
        title: 'Loitering (Berputar di Satu Area)',
        desc: 'Kapal tercatat bergerak dalam radius kecil (< 5 km) selama beberapa kali observasi. Indikasi kapal berputar tanpa tujuan jelas.',
        why_critical: 'MEDIUM karena belum tentu mencurigakan, tapi perlu diperhatikan terutama di zona strategis.',
        action: 'Kemungkinan: ship-to-ship transfer, menunggu order, fishing ilegal, atau surveillance.',
    },
    POSITION_JUMP: {
        title: 'Position Jump / AIS Spoofing',
        desc: 'Posisi kapal melompat jauh dalam waktu singkat (implied speed > 60 km/h) yang tidak mungkin untuk kapal laut. Indikasi pemalsuan data AIS.',
        why_critical: 'CRITICAL karena ini indikasi kuat manipulasi AIS yang disengaja.',
        action: 'Verifikasi identitas kapal, cek apakah MMSI digunakan ganda, laporkan ke IMO.',
    },
};

export default function AnalyticsPage() {
    const { axiosAuth } = useAuth();
    const navigate = useNavigate();
    const [analysis, setAnalysis] = useState(null);
    const [aiReport, setAiReport] = useState(null);
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [generatingAI, setGeneratingAI] = useState(false);
    const [expandedZone, setExpandedZone] = useState(null);
    const [sevFilter, setSevFilter] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [expandedType, setExpandedType] = useState(null);
    const [infoModal, setInfoModal] = useState(null);
    const [scheduleInterval, setScheduleInterval] = useState(60);
    const [scheduleEnabled, setScheduleEnabled] = useState(false);
    const [savingSchedule, setSavingSchedule] = useState(false);

    const fetchData = useCallback(async () => {
        try {
            const api = axiosAuth();
            const [analysisRes, aiRes, schedRes] = await Promise.all([
                api.get('/ext/analytics/latest').catch(() => ({ data: null })),
                api.get('/ext/analytics/ai-report').catch(() => ({ data: null })),
                api.get('/analytics/schedule').catch(() => ({ data: { enabled: false, interval_minutes: 60 } })),
            ]);
            if (analysisRes.data && !analysisRes.data.message) setAnalysis(analysisRes.data);
            if (aiRes.data && !aiRes.data.message) setAiReport(aiRes.data);
            if (schedRes.data) {
                setScheduleEnabled(schedRes.data.enabled || false);
                setScheduleInterval(schedRes.data.interval_minutes || 60);
            }
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

    const saveSchedule = async () => {
        setSavingSchedule(true);
        try {
            const api = axiosAuth();
            await api.post('/analytics/schedule', { enabled: scheduleEnabled, interval_minutes: scheduleInterval });
        } catch (err) { console.error(err); }
        setSavingSchedule(false);
    };

    const s = analysis?.summary || {};
    const zones = analysis?.zone_reports || {};
    const allAnomalies = analysis?.anomalies || [];
    const anomalies = allAnomalies.filter(a =>
        (!sevFilter || a.severity === sevFilter) &&
        (!typeFilter || a.type === typeFilter)
    );

    // Group anomalies by type for summary cards
    const anomalyGroups = {};
    for (const a of allAnomalies) {
        const t = a.type || 'OTHER';
        if (!anomalyGroups[t]) anomalyGroups[t] = [];
        anomalyGroups[t].push(a);
    }

    const goToVessel = (shipId) => {
        if (shipId) navigate(`/track/${shipId}`);
    };

    if (loading) return <div className="flex items-center justify-center min-h-screen"><Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" /></div>;

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-5" data-testid="analytics-page">
            {/* Info Modal */}
            {infoModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setInfoModal(null)}>
                    <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-6 max-w-lg w-full mx-4" onClick={e => e.stopPropagation()}>
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-bold text-[#F8FAFC]" style={{ fontFamily: 'Chivo, sans-serif' }}>{infoModal.title}</h3>
                            <button onClick={() => setInfoModal(null)} className="text-[#64748B] hover:text-[#F8FAFC]"><X className="w-5 h-5" /></button>
                        </div>
                        <div className="space-y-3 text-sm">
                            <div><span className="text-[#64748B] text-xs uppercase">Deskripsi</span><p className="text-[#F8FAFC] mt-1">{infoModal.desc}</p></div>
                            <div><span className="text-[#64748B] text-xs uppercase">Kenapa Severity Ini?</span><p className="text-[#F59E0B] mt-1">{infoModal.why_critical}</p></div>
                            <div><span className="text-[#64748B] text-xs uppercase">Rekomendasi Aksi</span><p className="text-[#10B981] mt-1">{infoModal.action}</p></div>
                        </div>
                    </div>
                </div>
            )}

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

            {/* Schedule Settings */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-4">
                <div className="flex items-center gap-3 flex-wrap">
                    <Clock className="w-4 h-4 text-[#00A6FB]" />
                    <span className="text-sm text-[#F8FAFC] font-medium">Penjadwalan Analisis:</span>
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={scheduleEnabled} onChange={e => setScheduleEnabled(e.target.checked)}
                            className="w-4 h-4 accent-[#00A6FB]" data-testid="schedule-enabled" />
                        <span className="text-sm text-[#94A3B8]">{scheduleEnabled ? 'Aktif' : 'Nonaktif'}</span>
                    </label>
                    <select value={scheduleInterval} onChange={e => setScheduleInterval(Number(e.target.value))}
                        className="bg-[#050A10] border border-[#1E293B] rounded px-3 py-1.5 text-sm text-[#F8FAFC]" data-testid="schedule-interval">
                        <option value={30}>Setiap 30 menit</option>
                        <option value={60}>Setiap 1 jam</option>
                        <option value={120}>Setiap 2 jam</option>
                        <option value={360}>Setiap 6 jam</option>
                        <option value={720}>Setiap 12 jam</option>
                        <option value={1440}>Setiap 24 jam</option>
                    </select>
                    <button onClick={saveSchedule} disabled={savingSchedule}
                        className="text-sm bg-[#00A6FB] hover:bg-[#008CD4] text-white px-3 py-1.5 rounded transition-all" data-testid="save-schedule-btn">
                        {savingSchedule ? 'Saving...' : 'Save'}
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
                    {/* Summary Cards - CLICKABLE */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                        {[
                            { label: 'Total Anomali', value: s.total_anomalies, color: '#F43F5E', filter: '' },
                            { label: 'CRITICAL', value: s.critical, color: '#F43F5E', filter: 'CRITICAL', sev: true },
                            { label: 'HIGH', value: s.high, color: '#F59E0B', filter: 'HIGH', sev: true },
                            { label: 'Zone Intrusion', value: s.zone_intrusions, color: '#A855F7', filter: 'ZONE_INTRUSION', type: true },
                            { label: 'AIS Gap', value: s.ais_gaps, color: '#06B6D4', filter: 'AIS_GAP', type: true },
                            { label: 'Loitering', value: s.loitering_detected, color: '#10B981', filter: 'LOITERING', type: true },
                        ].map((c, i) => (
                            <button key={i}
                                onClick={() => {
                                    if (c.sev) { setSevFilter(sevFilter === c.filter ? '' : c.filter); setTypeFilter(''); }
                                    else if (c.type) { setTypeFilter(typeFilter === c.filter ? '' : c.filter); setSevFilter(''); }
                                    else { setSevFilter(''); setTypeFilter(''); }
                                }}
                                className={`stat-card text-left transition-all hover:scale-[1.02] cursor-pointer ${
                                    (c.sev && sevFilter === c.filter) || (c.type && typeFilter === c.filter) ? 'ring-2 ring-[#00A6FB]' : ''
                                }`}>
                                <span className="text-[10px] text-[#64748B] uppercase tracking-[0.15em]">{c.label}</span>
                                <p className="text-2xl font-bold mt-1" style={{ color: c.color, fontFamily: 'Chivo, sans-serif' }}>{c.value || 0}</p>
                            </button>
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
                                            <div className="max-h-[200px] overflow-y-auto">
                                                <table className="data-table text-xs">
                                                    <thead><tr><th>Nama</th><th>Flag</th><th>Type</th><th>Speed</th><th>Posisi</th><th>Aksi</th></tr></thead>
                                                    <tbody>
                                                        {z.foreign_vessel_list.map((fv, i) => (
                                                            <tr key={i}>
                                                                <td className="font-medium">{fv.name}</td>
                                                                <td>
                                                                    {fv.flag && <img src={`https://flagcdn.com/w20/${fv.flag.toLowerCase()}.png`} alt="" className="w-4 h-3 inline mr-1 rounded-sm" onError={e => e.target.style.display = 'none'} />}
                                                                    {fv.flag}
                                                                </td>
                                                                <td className="text-[#94A3B8]">{fv.type}</td>
                                                                <td className="font-mono">{fv.speed} kn</td>
                                                                <td className="font-mono text-[#64748B]">{fv.lat?.toFixed(3)}, {fv.lon?.toFixed(3)}</td>
                                                                <td>
                                                                    <button onClick={() => goToVessel(fv.ship_id)}
                                                                        className="text-[#00A6FB] hover:text-[#008CD4] flex items-center gap-1 transition-colors">
                                                                        <ExternalLink className="w-3 h-3" /> Track
                                                                    </button>
                                                                </td>
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

                    {/* Anomalies - with explanations and vessel links */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between flex-wrap gap-2">
                            <h2 className="text-sm font-bold text-[#F8FAFC] uppercase tracking-[0.1em]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                                <AlertTriangle className="w-4 h-4 inline mr-2 text-[#F59E0B]" />
                                Anomali Terdeteksi ({anomalies.length})
                            </h2>
                            <div className="flex gap-1 flex-wrap">
                                {['', 'CRITICAL', 'HIGH', 'MEDIUM'].map(sev => (
                                    <button key={sev} onClick={() => { setSevFilter(sevFilter === sev ? '' : sev); setTypeFilter(''); }}
                                        className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${sevFilter === sev ? 'bg-[#00A6FB] text-white' : 'text-[#94A3B8] hover:text-[#F8FAFC]'}`}>
                                        {sev || 'ALL'}
                                    </button>
                                ))}
                                <span className="text-[#1E293B] mx-1">|</span>
                                {Object.keys(TYPE_LABELS).map(t => (
                                    <button key={t} onClick={() => { setTypeFilter(typeFilter === t ? '' : t); setSevFilter(''); }}
                                        className={`px-2 py-1 rounded text-[10px] font-medium transition-colors ${typeFilter === t ? 'bg-[#00A6FB] text-white' : 'text-[#94A3B8] hover:text-[#F8FAFC]'}`}>
                                        {TYPE_LABELS[t]}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Type explanation banner */}
                        {typeFilter && TYPE_EXPLANATIONS[typeFilter] && (
                            <div className="bg-[#050A10] border border-[#1E293B] rounded-md p-3 flex items-start gap-3">
                                <Info className="w-4 h-4 text-[#00A6FB] mt-0.5 flex-shrink-0" />
                                <div className="text-xs space-y-1">
                                    <p className="font-bold text-[#F8FAFC]">{TYPE_EXPLANATIONS[typeFilter].title}</p>
                                    <p className="text-[#94A3B8]">{TYPE_EXPLANATIONS[typeFilter].desc}</p>
                                    <p className="text-[#F59E0B]">Severity: {TYPE_EXPLANATIONS[typeFilter].why_critical}</p>
                                </div>
                            </div>
                        )}

                        <div className="max-h-[500px] overflow-y-auto space-y-1.5">
                            {anomalies.slice(0, 100).map((a, i) => (
                                <div key={i} className={`border rounded-md px-3 py-2 text-xs ${SEV_COLORS[a.severity] || 'bg-[#050A10] text-[#94A3B8]'}`}>
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-bold">[{a.severity}]</span>
                                        <button onClick={() => setInfoModal(TYPE_EXPLANATIONS[a.type])} className="font-medium underline decoration-dotted cursor-help hover:opacity-80">
                                            {TYPE_LABELS[a.type] || a.type}
                                        </button>
                                        {a.vessel && (
                                            <button onClick={() => goToVessel(a.vessel.ship_id)}
                                                className="flex items-center gap-1 text-[#F8FAFC] hover:text-[#00A6FB] transition-colors">
                                                {a.vessel.flag && <img src={`https://flagcdn.com/w20/${a.vessel.flag.toLowerCase()}.png`} alt="" className="w-4 h-3 inline rounded-sm" onError={e => e.target.style.display = 'none'} />}
                                                <span className="font-medium underline">{a.vessel.name}</span>
                                                <span className="text-[#64748B]">[{a.vessel.flag}]</span>
                                                <ExternalLink className="w-3 h-3 text-[#00A6FB]" />
                                            </button>
                                        )}
                                        {a.zone_name && <span className="text-[#A855F7]">{a.zone_name}</span>}
                                    </div>
                                    <p className="mt-1 opacity-80">{a.detail}</p>
                                    {a.vessel && a.vessel.lat && (
                                        <p className="mt-0.5 text-[#64748B]">
                                            Posisi: {a.vessel.lat?.toFixed(4)}, {a.vessel.lon?.toFixed(4)}
                                        </p>
                                    )}
                                </div>
                            ))}
                            {anomalies.length === 0 && (
                                <p className="text-center text-[#64748B] py-8">Tidak ada anomali dengan filter ini</p>
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
