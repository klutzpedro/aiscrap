import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Anchor, LayoutDashboard, Ship, ScrollText, Settings, LogOut, Menu, X, Route, Shield } from 'lucide-react';
import { useState } from 'react';

const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/vessels', label: 'Vessels', icon: Ship },
    { path: '/track', label: 'Vessel Track', icon: Route },
    { path: '/analytics', label: 'Intelligence', icon: Shield },
    { path: '/logs', label: 'Logs', icon: ScrollText },
    { path: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
    const { logout, user } = useAuth();
    const navigate = useNavigate();
    const [mobileOpen, setMobileOpen] = useState(false);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <>
            {/* Mobile toggle */}
            <button
                data-testid="sidebar-mobile-toggle"
                className="md:hidden fixed top-4 left-4 z-50 bg-[#0F1621] border border-[#1E293B] rounded-md p-2 text-[#F8FAFC]"
                onClick={() => setMobileOpen(!mobileOpen)}
            >
                {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>

            {/* Overlay */}
            {mobileOpen && (
                <div className="md:hidden fixed inset-0 bg-black/50 z-30" onClick={() => setMobileOpen(false)} />
            )}

            <aside className={`app-sidebar ${mobileOpen ? 'open' : ''}`}>
                {/* Logo */}
                <div className="p-5 border-b border-[#1E293B]">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 bg-[#00A6FB] rounded-md flex items-center justify-center flex-shrink-0">
                            <Anchor className="w-4 h-4 text-white" />
                        </div>
                        <div>
                            <h1 className="text-base font-bold text-[#F8FAFC]" style={{ fontFamily: 'Chivo, sans-serif' }}>
                                AIS Extractor
                            </h1>
                            <p className="text-[10px] text-[#64748B] uppercase tracking-[0.2em]">
                                ASEAN Region
                            </p>
                        </div>
                    </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1 p-3 space-y-1" data-testid="sidebar-nav">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            data-testid={`nav-${item.path.slice(1)}`}
                            onClick={() => setMobileOpen(false)}
                            className={({ isActive }) =>
                                `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors duration-200 ${
                                    isActive
                                        ? 'bg-[#00A6FB]/10 text-[#00A6FB] border border-[#00A6FB]/20'
                                        : 'text-[#94A3B8] hover:bg-[#172233] hover:text-[#F8FAFC] border border-transparent'
                                }`
                            }
                        >
                            <item.icon className="w-4 h-4" />
                            <span>{item.label}</span>
                        </NavLink>
                    ))}
                </nav>

                {/* User & Logout */}
                <div className="p-4 border-t border-[#1E293B]">
                    <div className="flex items-center gap-3 mb-3 px-1">
                        <div className="w-8 h-8 rounded-full bg-[#172233] flex items-center justify-center text-[#00A6FB] text-xs font-bold">
                            {user?.name?.[0] || 'A'}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm text-[#F8FAFC] truncate">{user?.name || 'Admin'}</p>
                            <p className="text-xs text-[#64748B] truncate">{user?.role || 'admin'}</p>
                        </div>
                    </div>
                    <button
                        data-testid="logout-button"
                        onClick={handleLogout}
                        className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-[#F43F5E] hover:bg-[#F43F5E]/10 transition-colors duration-200"
                    >
                        <LogOut className="w-4 h-4" />
                        <span>Sign Out</span>
                    </button>
                </div>
            </aside>
        </>
    );
}
