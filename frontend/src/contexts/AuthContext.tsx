"use client";
import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { api, ApiRequestError, invalidateSessionRequests, SESSION_EXPIRED } from "@/lib/api";
import { setStorageAccount, protectLegacyAccountData } from "@/lib/accountStorage";

export interface User { id: string; name: string; email: string; subscription_tier: string; avatar_url: string | null; }
interface AuthContextValue {
    user: User | null; isLoading: boolean; isAuthenticated: boolean; sessionError: string;
    login: (email: string, password: string, remember?: boolean) => Promise<void>;
    register: (name: string, email: string, password: string) => Promise<void>;
    logout: () => Promise<void>; reloadSession: () => Promise<void>;
}
const AuthContext = createContext<AuthContextValue | null>(null);
const SYNC_KEY = "corten_auth_changed";
const LOGOUT_KEY = "corten_logout_pending";
let logoutPending = false;
let logoutRequest: Promise<void> | null = null;
function pendingLogout() {
    try { return logoutPending || localStorage.getItem(LOGOUT_KEY) === "true"; } catch { return logoutPending; }
}
async function completeLogout() {
    if (!logoutRequest) logoutRequest = api.post<void>("/api/v1/auth/logout", {}).then(() => {
        logoutPending = false;
        try { localStorage.removeItem(LOGOUT_KEY); } catch { /* ignore */ }
    }).finally(() => { logoutRequest = null; });
    return logoutRequest;
}
const LOGOUT_ERROR = "Sign-out could not be completed. Private views are hidden. Retry when connected.";
export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [sessionError, setSessionError] = useState("");
    const version = useRef(0);
    const apply = useCallback((next: User | null) => {
        setStorageAccount(next?.id || null);
        setUser(next);
        setIsLoading(false);
    }, []);
    const broadcast = () => {
        try { localStorage.setItem(SYNC_KEY, `${Date.now()}:${Math.random()}`); } catch { /* Storage can be unavailable. */ }
    };
    const reloadSession = useCallback(async () => {
        const current = ++version.current;
        if (pendingLogout()) {
            apply(null);
            try { await completeLogout(); if (current === version.current) setSessionError(""); }
            catch { if (current === version.current) setSessionError(LOGOUT_ERROR); }
            return;
        }
        try {
            const profile = await api.get<User | null>("/api/v1/auth/session");
            if (current === version.current) { setSessionError(""); apply(profile); }
        } catch (error) {
            if (current !== version.current) return;
            if (error instanceof ApiRequestError && error.status === 401) { setSessionError(""); apply(null); }
            else { setSessionError("Unable to verify your session. Please retry."); setIsLoading(false); }
        }
    }, [apply]);
    useEffect(() => {
        protectLegacyAccountData();
        for (const key of ["corten_access_token", "corten_refresh_token", "corten_user"]) {
            try { localStorage.removeItem(key); sessionStorage.removeItem(key); } catch { /* ignore */ }
        }
        void reloadSession();
        const expired = () => { version.current++; invalidateSessionRequests(); setSessionError(""); apply(null); };
        const sync = (event: StorageEvent) => { if (event.key === SYNC_KEY) { invalidateSessionRequests(); apply(null); setIsLoading(true); void reloadSession(); } };
        const focus = () => { void reloadSession(); };
        window.addEventListener(SESSION_EXPIRED, expired);
        window.addEventListener("storage", sync);
        window.addEventListener("focus", focus);
        window.addEventListener("online", focus);
        return () => { version.current++; window.removeEventListener(SESSION_EXPIRED, expired); window.removeEventListener("storage", sync); window.removeEventListener("focus", focus); window.removeEventListener("online", focus); };
    }, [apply, reloadSession]);
    const login = useCallback(async (email: string, password: string, remember = false) => {
        if (pendingLogout()) await completeLogout();
        const current = ++version.current;
        const data = await api.post<{ user: User }>("/api/v1/auth/login", { email: email.trim(), password, remember_me: remember });
        if (current === version.current) { invalidateSessionRequests(); setSessionError(""); apply(data.user); broadcast(); }
    }, [apply]);
    const register = useCallback(async (name: string, email: string, password: string) => {
        if (pendingLogout()) await completeLogout();
        const current = ++version.current;
        const data = await api.post<{ user: User }>("/api/v1/auth/register", { name: name.trim(), email: email.trim(), password });
        if (current === version.current) { invalidateSessionRequests(); setSessionError(""); apply(data.user); broadcast(); }
    }, [apply]);
    const logout = useCallback(async () => {
        version.current++;
        invalidateSessionRequests();
        logoutPending = true;
        try { localStorage.setItem(LOGOUT_KEY, "true"); } catch { /* The in-memory guard still hides private views. */ }
        apply(null);
        broadcast();
        try { await completeLogout(); setSessionError(""); }
        catch { setSessionError(LOGOUT_ERROR); }
        finally { broadcast(); }
    }, [apply]);
    return <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, sessionError, login, register, logout, reloadSession }}>
        {isLoading ? <div role="status" style={{ padding: "32px", color: "var(--text-secondary)" }}>Loading Corten…</div> :
            <div key={user?.id || "guest"} style={{ display: "contents" }}>{children}</div>}
    </AuthContext.Provider>;
}
export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) throw new Error("useAuth must be used inside AuthProvider");
    return context;
}
