import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { ScrollText, ChevronLeft, ChevronRight, CheckCircle2, XCircle, Loader2, Send } from 'lucide-react';

export default function LogsPage() {
    const { axiosAuth } = useAuth();
    const [logs, setLogs] = useState([]);
    const [forwardLogs, setForwardLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState('extraction');

    const fetchLogs = useCallback(async () => {
        setLoading(true);
        try {
            const api = axiosAuth();
            const [logsRes, fwdRes] = await Promise.all([
                api.get('/bot/logs', { params: { page, limit: 20 } }),
                api.get('/forward/logs?limit=50'),
            ]);
            setLogs(logsRes.data.logs || []);
            setTotal(logsRes.data.total || 0);
            setPages(logsRes.data.pages || 0);
            setForwardLogs(fwdRes.data.logs || []);
        } catch (err) {
            console.error('Fetch logs error:', err);
        }
        setLoading(false);
    }, [axiosAuth, page]);

    useEffect(() => { fetchLogs(); }, [fetchLogs]);

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-6" data-testid="logs-page">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-[#F8FAFC] tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    Logs
                </h1>
                <p className="text-sm text-[#94A3B8] mt-1">
                    Extraction & API forwarding logs
                </p>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-[#0F1621] border border-[#1E293B] rounded-md p-1 w-fit">
                <button
                    data-testid="tab-extraction"
                    onClick={() => setTab('extraction')}
                    className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                        tab === 'extraction' ? 'bg-[#00A6FB] text-white' : 'text-[#94A3B8] hover:text-[#F8FAFC]'
                    }`}
                >
                    Extraction Logs ({total})
                </button>
                <button
                    data-testid="tab-forward"
                    onClick={() => setTab('forward')}
                    className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                        tab === 'forward' ? 'bg-[#00A6FB] text-white' : 'text-[#94A3B8] hover:text-[#F8FAFC]'
                    }`}
                >
                    Forward Logs ({forwardLogs.length})
                </button>
            </div>

            {/* Extraction Logs Tab */}
            {tab === 'extraction' && (
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md overflow-hidden">
                    {loading ? (
                        <div className="flex items-center justify-center py-16">
                            <Loader2 className="w-6 h-6 text-[#00A6FB] animate-spin" />
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="data-table" data-testid="logs-table">
                                <thead>
                                    <tr>
                                        <th>Status</th>
                                        <th>Timestamp</th>
                                        <th>Source</th>
                                        <th>Vessels</th>
                                        <th>Duration</th>
                                        <th>Error</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {logs.map((log, i) => (
                                        <tr key={log.id || i} data-testid={`log-row-${i}`}>
                                            <td>
                                                {log.status === 'success' ? (
                                                    <span className="flex items-center gap-1.5 text-[#10B981] text-xs font-medium">
                                                        <CheckCircle2 className="w-3.5 h-3.5" /> Success
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center gap-1.5 text-[#F43F5E] text-xs font-medium">
                                                        <XCircle className="w-3.5 h-3.5" /> Failed
                                                    </span>
                                                )}
                                            </td>
                                            <td className="font-mono text-xs text-[#94A3B8] whitespace-nowrap">
                                                {new Date(log.timestamp).toLocaleString()}
                                            </td>
                                            <td>
                                                <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                                                    log.source === 'marinetraffic'
                                                        ? 'bg-[#00A6FB]/15 text-[#00A6FB]'
                                                        : 'bg-[#F59E0B]/15 text-[#F59E0B]'
                                                }`}>
                                                    {log.source}
                                                </span>
                                            </td>
                                            <td className="font-mono text-sm">{log.vessels_count}</td>
                                            <td className="font-mono text-xs text-[#94A3B8]">{log.duration_seconds}s</td>
                                            <td className="text-xs text-[#F43F5E] max-w-[200px] truncate">{log.error_message || '-'}</td>
                                        </tr>
                                    ))}
                                    {logs.length === 0 && (
                                        <tr>
                                            <td colSpan="6" className="text-center text-[#64748B] py-12">
                                                <ScrollText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                                No extraction logs yet
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {pages > 1 && (
                        <div className="flex items-center justify-between px-4 py-3 border-t border-[#1E293B]">
                            <span className="text-xs text-[#64748B]">Page {page} of {pages}</span>
                            <div className="flex gap-1">
                                <button data-testid="logs-prev-page" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                                    className="p-1.5 rounded-md text-[#94A3B8] hover:bg-[#172233] disabled:opacity-30 transition-colors">
                                    <ChevronLeft className="w-4 h-4" />
                                </button>
                                <button data-testid="logs-next-page" onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page >= pages}
                                    className="p-1.5 rounded-md text-[#94A3B8] hover:bg-[#172233] disabled:opacity-30 transition-colors">
                                    <ChevronRight className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Forward Logs Tab */}
            {tab === 'forward' && (
                <div className="bg-[#0F1621] border border-[#1E293B] rounded-md overflow-hidden">
                    {loading ? (
                        <div className="flex items-center justify-center py-16">
                            <Loader2 className="w-6 h-6 text-[#00A6FB] animate-spin" />
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="data-table" data-testid="forward-logs-table">
                                <thead>
                                    <tr>
                                        <th>Status</th>
                                        <th>Timestamp</th>
                                        <th>Endpoint</th>
                                        <th>Vessels Sent</th>
                                        <th>HTTP Code</th>
                                        <th>Error</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {forwardLogs.map((log, i) => (
                                        <tr key={log.id || i}>
                                            <td>
                                                {log.success ? (
                                                    <span className="flex items-center gap-1.5 text-[#10B981] text-xs font-medium">
                                                        <CheckCircle2 className="w-3.5 h-3.5" /> Sent
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center gap-1.5 text-[#F43F5E] text-xs font-medium">
                                                        <XCircle className="w-3.5 h-3.5" /> Failed
                                                    </span>
                                                )}
                                            </td>
                                            <td className="font-mono text-xs text-[#94A3B8] whitespace-nowrap">
                                                {new Date(log.timestamp).toLocaleString()}
                                            </td>
                                            <td className="text-xs text-[#94A3B8] max-w-[250px] truncate">{log.endpoint}</td>
                                            <td className="font-mono text-sm">{log.vessels_sent}</td>
                                            <td>
                                                <span className={`font-mono text-xs ${log.success ? 'text-[#10B981]' : 'text-[#F43F5E]'}`}>
                                                    {log.status_code || '-'}
                                                </span>
                                            </td>
                                            <td className="text-xs text-[#F43F5E] max-w-[200px] truncate">{log.error || '-'}</td>
                                        </tr>
                                    ))}
                                    {forwardLogs.length === 0 && (
                                        <tr>
                                            <td colSpan="6" className="text-center text-[#64748B] py-12">
                                                <Send className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                                No forward logs yet. Configure API Forwarding in Settings.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
