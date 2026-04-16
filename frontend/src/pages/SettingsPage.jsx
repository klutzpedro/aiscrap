import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { Settings, Play, Pause, Save, Send, Loader2, Wifi, WifiOff, Clock, Globe } from 'lucide-react';

export default function SettingsPage() {
    const { axiosAuth } = useAuth();
    const [botStatus, setBotStatus] = useState(null);
    const [interval, setInterval_] = useState(30);
    const [forwardConfig, setForwardConfig] = useState({ endpoint_url: '', method: 'POST', headers: {}, enabled: false });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [sending, setSending] = useState(false);
    const [toggling, setToggling] = useState(false);
    const [msg, setMsg] = useState('');

    const fetchData = useCallback(async () => {
        try {
            const api = axiosAuth();
            const [botRes, fwdRes] = await Promise.all([
                api.get('/bot/status'),
                api.get('/forward/config'),
            ]);
            setBotStatus(botRes.data);
            setInterval_(botRes.data.interval_minutes || 30);
            setForwardConfig(fwdRes.data || { endpoint_url: '', method: 'POST', headers: {}, enabled: false });
        } catch (err) {
            console.error('Settings fetch error:', err);
        }
        setLoading(false);
    }, [axiosAuth]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const toggleBot = async () => {
        setToggling(true);
        try {
            const api = axiosAuth();
            if (botStatus?.running) {
                await api.post('/bot/stop');
            } else {
                await api.post('/bot/start');
            }
            await fetchData();
        } catch (err) {
            console.error('Toggle bot error:', err);
        }
        setToggling(false);
    };

    const updateInterval = async () => {
        setSaving(true);
        try {
            const api = axiosAuth();
            await api.post(`/bot/settings?interval_minutes=${interval}`);
            setMsg('Interval updated');
            setTimeout(() => setMsg(''), 3000);
            await fetchData();
        } catch (err) {
            console.error('Update interval error:', err);
        }
        setSaving(false);
    };

    const saveForwardConfig = async () => {
        setSaving(true);
        try {
            const api = axiosAuth();
            await api.post('/forward/config', forwardConfig);
            setMsg('API forwarding config saved');
            setTimeout(() => setMsg(''), 3000);
        } catch (err) {
            console.error('Save forward config error:', err);
        }
        setSaving(false);
    };

    const sendNow = async () => {
        setSending(true);
        try {
            const api = axiosAuth();
            const res = await api.post('/forward/send');
            setMsg(`Data sent: ${res.data.vessels_sent} vessels (status ${res.data.status_code})`);
            setTimeout(() => setMsg(''), 5000);
        } catch (err) {
            const detail = err.response?.data?.detail;
            setMsg(`Send failed: ${typeof detail === 'string' ? detail : 'Error'}`);
            setTimeout(() => setMsg(''), 5000);
        }
        setSending(false);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" />
            </div>
        );
    }

    return (
        <div className="p-4 md:p-6 lg:p-8 space-y-6" data-testid="settings-page">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-[#F8FAFC] tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    Settings
                </h1>
                <p className="text-sm text-[#94A3B8] mt-1">
                    Bot configuration & API forwarding
                </p>
            </div>

            {msg && (
                <div className="bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] text-sm rounded-md p-3" data-testid="settings-message">
                    {msg}
                </div>
            )}

            {/* Bot Control */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-6 space-y-5">
                <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center gap-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    <Settings className="w-5 h-5 text-[#00A6FB]" />
                    Bot Control
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Status */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-3">
                            <div className={`w-3 h-3 rounded-full ${botStatus?.running ? 'bg-[#10B981] animate-pulse' : 'bg-[#F43F5E]'}`} />
                            <span className="text-sm text-[#F8FAFC]">
                                Bot is <strong>{botStatus?.running ? 'Running' : 'Stopped'}</strong>
                            </span>
                        </div>

                        <button
                            data-testid="toggle-bot-button"
                            onClick={toggleBot}
                            disabled={toggling}
                            className={`flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium transition-all duration-200 active:scale-[0.98] ${
                                botStatus?.running
                                    ? 'bg-[#F43F5E] hover:bg-[#E11D48] text-white'
                                    : 'bg-[#10B981] hover:bg-[#059669] text-white'
                            }`}
                        >
                            {toggling ? <Loader2 className="w-4 h-4 animate-spin" /> : botStatus?.running ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                            {botStatus?.running ? 'Stop Bot' : 'Start Bot'}
                        </button>

                        <div className="space-y-2 text-sm">
                            <div className="flex items-center gap-2 text-[#94A3B8]">
                                <Clock className="w-3.5 h-3.5" />
                                <span>Total extractions: <strong className="text-[#F8FAFC]">{botStatus?.total_extractions || 0}</strong></span>
                            </div>
                            <div className="flex items-center gap-2 text-[#94A3B8]">
                                {botStatus?.mt_connected ? <Wifi className="w-3.5 h-3.5 text-[#10B981]" /> : <WifiOff className="w-3.5 h-3.5 text-[#F43F5E]" />}
                                <span>MarineTraffic: <strong className={botStatus?.mt_connected ? 'text-[#10B981]' : 'text-[#F43F5E]'}>{botStatus?.mt_connected ? 'Connected' : 'Not connected'}</strong></span>
                            </div>
                            {botStatus?.last_extraction && (
                                <div className="flex items-center gap-2 text-[#94A3B8]">
                                    <Clock className="w-3.5 h-3.5" />
                                    <span>Last: <span className="font-mono text-xs text-[#F8FAFC]">{new Date(botStatus.last_extraction).toLocaleString()}</span></span>
                                </div>
                            )}
                            {botStatus?.next_extraction && (
                                <div className="flex items-center gap-2 text-[#94A3B8]">
                                    <Clock className="w-3.5 h-3.5" />
                                    <span>Next: <span className="font-mono text-xs text-[#F8FAFC]">{new Date(botStatus.next_extraction).toLocaleString()}</span></span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Interval */}
                    <div className="space-y-4">
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] font-medium block">
                            Extraction Interval (minutes)
                        </label>
                        <div className="flex gap-3">
                            <input
                                data-testid="interval-input"
                                type="number"
                                min="1"
                                max="1440"
                                value={interval}
                                onChange={(e) => setInterval_(Number(e.target.value))}
                                className="w-32 bg-[#050A10] border border-[#1E293B] rounded-md px-4 py-2 text-[#F8FAFC] text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                            />
                            <button
                                data-testid="save-interval-button"
                                onClick={updateInterval}
                                disabled={saving}
                                className="flex items-center gap-2 bg-[#00A6FB] hover:bg-[#008CD4] text-white text-sm font-medium px-4 py-2 rounded-md transition-all duration-200 active:scale-[0.98]"
                            >
                                <Save className="w-4 h-4" />
                                Save
                            </button>
                        </div>
                        <p className="text-xs text-[#64748B]">
                            The bot will automatically extract vessel data at this interval when running.
                        </p>
                    </div>
                </div>
            </div>

            {/* API Forwarding */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-6 space-y-5">
                <h2 className="text-lg font-bold text-[#F8FAFC] flex items-center gap-2" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    <Globe className="w-5 h-5 text-[#00A6FB]" />
                    API Forwarding
                </h2>

                <div className="space-y-4">
                    <div>
                        <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] font-medium mb-1.5 block">
                            Endpoint URL
                        </label>
                        <input
                            data-testid="forward-url-input"
                            type="url"
                            value={forwardConfig.endpoint_url}
                            onChange={(e) => setForwardConfig(c => ({ ...c, endpoint_url: e.target.value }))}
                            placeholder="https://your-api.com/receive-data"
                            className="w-full bg-[#050A10] border border-[#1E293B] rounded-md px-4 py-2 text-[#F8FAFC] text-sm placeholder-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                        />
                    </div>

                    <div className="flex gap-4">
                        <div>
                            <label className="text-xs text-[#64748B] uppercase tracking-[0.15em] font-medium mb-1.5 block">Method</label>
                            <select
                                data-testid="forward-method-select"
                                value={forwardConfig.method}
                                onChange={(e) => setForwardConfig(c => ({ ...c, method: e.target.value }))}
                                className="bg-[#050A10] border border-[#1E293B] rounded-md px-4 py-2 text-[#F8FAFC] text-sm focus:outline-none focus:ring-2 focus:ring-[#00A6FB]"
                            >
                                <option value="POST">POST</option>
                                <option value="PUT">PUT</option>
                            </select>
                        </div>
                        <div className="flex items-end gap-2">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    data-testid="forward-enabled-checkbox"
                                    type="checkbox"
                                    checked={forwardConfig.enabled}
                                    onChange={(e) => setForwardConfig(c => ({ ...c, enabled: e.target.checked }))}
                                    className="w-4 h-4 accent-[#00A6FB]"
                                />
                                <span className="text-sm text-[#94A3B8]">Enabled</span>
                            </label>
                        </div>
                    </div>

                    <div className="flex gap-3">
                        <button
                            data-testid="save-forward-config-button"
                            onClick={saveForwardConfig}
                            disabled={saving}
                            className="flex items-center gap-2 bg-[#00A6FB] hover:bg-[#008CD4] text-white text-sm font-medium px-4 py-2 rounded-md transition-all duration-200 active:scale-[0.98]"
                        >
                            <Save className="w-4 h-4" />
                            Save Config
                        </button>
                        <button
                            data-testid="send-data-now-button"
                            onClick={sendNow}
                            disabled={sending || !forwardConfig.endpoint_url}
                            className="flex items-center gap-2 bg-[#172233] hover:bg-[#1E293B] text-[#F8FAFC] text-sm font-medium px-4 py-2 rounded-md border border-[#1E293B] transition-all duration-200 active:scale-[0.98] disabled:opacity-50"
                        >
                            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                            Send Data Now
                        </button>
                    </div>
                </div>
            </div>

            {/* MarineTraffic Info */}
            <div className="bg-[#0F1621] border border-[#1E293B] rounded-md p-6">
                <h2 className="text-lg font-bold text-[#F8FAFC] mb-3" style={{ fontFamily: 'Chivo, sans-serif' }}>
                    Data Source Info
                </h2>
                <div className="space-y-2 text-sm text-[#94A3B8]">
                    <p>The bot attempts to scrape vessel data from MarineTraffic for the ASEAN region.</p>
                    <p>If scraping fails (due to anti-bot protection), the system falls back to <strong className="text-[#F59E0B]">simulated data</strong> for demonstration.</p>
                    <p>Bounding box: <span className="font-mono text-[#F8FAFC]">Lat -11.0 to 25.0, Lon 95.0 to 150.0</span></p>
                    <p>For production use, consider using the official <a href="https://www.marinetraffic.com/en/p/api-services" target="_blank" rel="noopener noreferrer" className="text-[#00A6FB] hover:underline">MarineTraffic API</a>.</p>
                </div>
            </div>
        </div>
    );
}
