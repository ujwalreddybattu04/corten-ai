"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, ApiRequestError } from "@/lib/api";

interface User {
    id: string;
    name: string;
    email: string;
    subscription_tier: string;
    avatar_url: string | null;
}

interface AuthState {
    user: User | null;
    accessToken: string | null;
    isLoading: boolean;
    isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
    login: (email: string, password: string) => Promise<void>;
    register: (name: string, email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY     = "corten_access_token";
const REFRESH_KEY   = "corten_refresh_token";
const USER_KEY      = "corten_user";

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [state, setState] = useState<AuthState>({
        user: null,
        accessToken: null,
        isLoading: true,
        isAuthenticated: false,
    });

    // Rehydrate from localStorage on mount
    useEffect(() => {
        try {
            const token = localStorage.getItem(TOKEN_KEY);
            const userRaw = localStorage.getItem(USER_KEY);
            if (token && userRaw) {
                const user = JSON.parse(userRaw) as User;
                setState({ user, accessToken: token, isLoading: false, isAuthenticated: true });
                return;
            }
        } catch { /* ignore */ }
        setState(s => ({ ...s, isLoading: false }));
    }, []);

    const persistAuth = (user: User, accessToken: string, refreshToken: string) => {
        localStorage.setItem(TOKEN_KEY, accessToken);
        localStorage.setItem(REFRESH_KEY, refreshToken);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
        setState({ user, accessToken, isLoading: false, isAuthenticated: true });
    };

    const login = useCallback(async (email: string, password: string) => {
        const data = await api.post<{
            user: User; access_token: string; refresh_token: string;
        }>("/api/v1/auth/login", { email, password });
        persistAuth(data.user, data.access_token, data.refresh_token);
    }, []);

    const register = useCallback(async (name: string, email: string, password: string) => {
        const data = await api.post<{
            user: User; access_token: string; refresh_token: string;
        }>("/api/v1/auth/register", { name, email, password });
        persistAuth(data.user, data.access_token, data.refresh_token);
    }, []);

    const logout = useCallback(async () => {
        const refreshToken = localStorage.getItem(REFRESH_KEY);
        try {
            if (refreshToken) {
                await api.post("/api/v1/auth/logout", { refresh_token: refreshToken });
            }
        } catch { /* ignore — clear local state regardless */ }
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
        setState({ user: null, accessToken: null, isLoading: false, isAuthenticated: false });
    }, []);

    return (
        <AuthContext.Provider value={{ ...state, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
    return ctx;
}
