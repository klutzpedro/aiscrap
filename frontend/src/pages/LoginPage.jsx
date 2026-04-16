import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Anchor, Loader2, AlertCircle } from 'lucide-react';

export default function LoginPage() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            await login(email, password);
            navigate('/dashboard');
        } catch (err) {
            const detail = err.response?.data?.detail;
            if (typeof detail === 'string') setError(detail);
            else if (Array.isArray(detail)) setError(detail.map(d => d.msg || JSON.stringify(d)).join(' '));
            else setError('Login failed. Please check your credentials.');
        }
        setLoading(false);
    };

    return (
        <div className="min-h-screen flex items-center justify-center relative overflow-hidden" data-testid="login-page">
            {/* Background */}
            <div className="absolute inset-0 z-0">
                <img
                    src="https://images.unsplash.com/photo-1774646598677-cc38cb3cac00?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODd8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMGdsb3dpbmclMjBtYXB8ZW58MHx8fHwxNzc2MzE3NzIwfDA&ixlib=rb-4.1.0&q=85"
                    alt=""
                    className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 bg-[#050A10]/80" />
            </div>

            {/* Login Card */}
            <div className="relative z-10 w-full max-w-md mx-4 animate-fade-up">
                <div className="bg-[#0F1621]/90 backdrop-blur-xl border border-[#1E293B] rounded-md p-8">
                    {/* Logo */}
                    <div className="flex items-center gap-3 mb-8">
                        <div className="w-10 h-10 bg-[#00A6FB] rounded-md flex items-center justify-center">
                            <Anchor className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-[#F8FAFC]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                                AIS Extractor
                            </h1>
                            <p className="text-xs text-[#64748B] uppercase tracking-[0.2em]">
                                ASEAN Maritime Intel
                            </p>
                        </div>
                    </div>

                    <h2 className="text-2xl font-bold text-[#F8FAFC] mb-1" style={{ fontFamily: 'Chivo, sans-serif' }}>
                        Sign In
                    </h2>
                    <p className="text-sm text-[#94A3B8] mb-6">
                        Access vessel tracking dashboard
                    </p>

                    {error && (
                        <div className="flex items-center gap-2 bg-[#F43F5E]/10 border border-[#F43F5E]/30 text-[#F43F5E] text-sm rounded-md p-3 mb-4" data-testid="login-error">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="text-xs text-[#94A3B8] uppercase tracking-[0.15em] font-medium mb-1.5 block">
                                Username
                            </label>
                            <input
                                data-testid="login-email-input"
                                type="text"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full bg-[#050A10] border border-[#1E293B] rounded-md px-4 py-2.5 text-[#F8FAFC] text-sm placeholder-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00A6FB] focus:border-transparent transition-all"
                                placeholder="Enter username"
                                required
                            />
                        </div>
                        <div>
                            <label className="text-xs text-[#94A3B8] uppercase tracking-[0.15em] font-medium mb-1.5 block">
                                Password
                            </label>
                            <input
                                data-testid="login-password-input"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full bg-[#050A10] border border-[#1E293B] rounded-md px-4 py-2.5 text-[#F8FAFC] text-sm placeholder-[#64748B] focus:outline-none focus:ring-2 focus:ring-[#00A6FB] focus:border-transparent transition-all"
                                placeholder="Enter password"
                                required
                            />
                        </div>
                        <button
                            data-testid="login-submit-button"
                            type="submit"
                            disabled={loading}
                            className="w-full bg-[#00A6FB] hover:bg-[#008CD4] active:scale-[0.98] text-white font-semibold py-2.5 rounded-md transition-all duration-200 flex items-center justify-center gap-2 disabled:opacity-60"
                        >
                            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                            {loading ? 'Signing In...' : 'Sign In'}
                        </button>
                    </form>

                    <p className="text-xs text-[#64748B] text-center mt-6">
                        AIS Data Extraction System &middot; ASEAN Region
                    </p>
                </div>
            </div>
        </div>
    );
}
