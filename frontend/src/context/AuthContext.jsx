import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [token, setToken] = useState(() => localStorage.getItem('ais_token'));

    const axiosAuth = useCallback(() => {
        const t = localStorage.getItem('ais_token');
        return axios.create({
            baseURL: API,
            headers: t ? { Authorization: `Bearer ${t}` } : {},
        });
    }, []);

    useEffect(() => {
        const checkAuth = async () => {
            const stored = localStorage.getItem('ais_token');
            if (!stored) {
                setLoading(false);
                return;
            }
            try {
                const res = await axios.get(`${API}/auth/me`, {
                    headers: { Authorization: `Bearer ${stored}` },
                });
                setUser(res.data);
                setToken(stored);
            } catch {
                localStorage.removeItem('ais_token');
                setToken(null);
                setUser(null);
            }
            setLoading(false);
        };
        checkAuth();
    }, []);

    const login = async (email, password) => {
        const res = await axios.post(`${API}/auth/login`, { email, password });
        const { token: newToken, user: userData } = res.data;
        localStorage.setItem('ais_token', newToken);
        setToken(newToken);
        setUser(userData);
        return userData;
    };

    const logout = () => {
        localStorage.removeItem('ais_token');
        setToken(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, token, loading, login, logout, axiosAuth }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be inside AuthProvider');
    return ctx;
}
