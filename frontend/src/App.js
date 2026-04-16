import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import VesselsPage from './pages/VesselsPage';
import LogsPage from './pages/LogsPage';
import SettingsPage from './pages/SettingsPage';
import Sidebar from './components/Sidebar';
import { Loader2 } from 'lucide-react';
import './App.css';

function ProtectedRoute({ children }) {
    const { user, loading } = useAuth();
    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#050A10]">
                <Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" />
            </div>
        );
    }
    if (!user) return <Navigate to="/login" replace />;
    return children;
}

function AppLayout({ children }) {
    return (
        <div className="app-layout">
            <Sidebar />
            <main className="app-main">{children}</main>
        </div>
    );
}

function AppRoutes() {
    const { user, loading } = useAuth();
    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-[#050A10]">
                <Loader2 className="w-8 h-8 text-[#00A6FB] animate-spin" />
            </div>
        );
    }
    return (
        <Routes>
            <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <LoginPage />} />
            <Route path="/dashboard" element={<ProtectedRoute><AppLayout><DashboardPage /></AppLayout></ProtectedRoute>} />
            <Route path="/vessels" element={<ProtectedRoute><AppLayout><VesselsPage /></AppLayout></ProtectedRoute>} />
            <Route path="/logs" element={<ProtectedRoute><AppLayout><LogsPage /></AppLayout></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><AppLayout><SettingsPage /></AppLayout></ProtectedRoute>} />
            <Route path="*" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />
        </Routes>
    );
}

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <AppRoutes />
            </AuthProvider>
        </BrowserRouter>
    );
}
