"use client";
import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { api, ApiRequestError, invalidateSessionRequests, SESSION_EXPIRED } from "@/lib/api";
import { setStorageAccount, getStorageAccount, protectLegacyAccountData, safeReturnPath } from "@/lib/accountStorage";
import { useSignInTransition } from "@/components/auth/useSignInTransition";
import SignOutDialog from "@/components/auth/SignOutDialog";
import { startCloudSync, stopCloudSync, markCloudStorageUnavailable, hasCloudSync } from "@/lib/cloudSync";
import { usePathname, useRouter } from "next/navigation";

export interface User { id: string; name: string; email: string; subscription_tier: string; avatar_url: string | null; }
interface AuthContextValue {
    user: User | null; isLoading: boolean; isAuthenticated: boolean; sessionError: string; isCompletingSignIn: boolean;
    login: (email: string, password: string, remember?: boolean) => Promise<void>;
    register: (name: string, email: string, password: string) => Promise<void>;
    logout: () => Promise<void>; requestLogout: () => void; reloadSession: () => Promise<void>;
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
    const pathname = usePathname();
    const router = useRouter();
    const publicPage = pathname?.startsWith("/auth/") === true;
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [sessionError, setSessionError] = useState("");
    const [logoutRequested, setLogoutRequested] = useState(false);
    const requestLogout = useCallback(() => setLogoutRequested(true), []);
    const { stage, active: isCompletingSignIn, begin: beginSignIn, cancel: cancelSignIn } =
        useSignInTransition(pathname, !!user && !isLoading);
    const version = useRef(0);
    const apply = useCallback(async (next: User | null) => {
        const generation = version.current;
        if (!next) { cancelSignIn(); setLogoutRequested(false); }
        const changed = getStorageAccount() !== (next?.id || null);
        if (changed || !next) stopCloudSync();
        setStorageAccount(next?.id || null);
        if (next && (changed || !hasCloudSync(next.id))) { setIsLoading(true); try { await startCloudSync(next.id); } catch { markCloudStorageUnavailable(); } }
        if (generation !== version.current) return;
        setUser(next);
        setIsLoading(false);
    }, [cancelSignIn]);
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
            if (current === version.current) { setSessionError(""); await apply(profile); }
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
        if (current !== version.current) return;
        const destination = safeReturnPath(new URLSearchParams(window.location.search).get("next"));
        try {
            await beginSignIn();
            if (current !== version.current) { cancelSignIn(); return; }
            invalidateSessionRequests(); setSessionError("");
            await apply(data.user);
            if (current !== version.current) { cancelSignIn(); return; }
            broadcast();
            router.replace(destination);
        } catch (error) { cancelSignIn(); throw error; }
    }, [apply, beginSignIn, cancelSignIn, router]);
    const register = useCallback(async (name: string, email: string, password: string) => {
        if (pendingLogout()) await completeLogout();
        const current = ++version.current;
        const data = await api.post<{ user: User }>("/api/v1/auth/register", { name: name.trim(), email: email.trim(), password });
        if (current === version.current) { invalidateSessionRequests(); setSessionError(""); await apply(data.user); broadcast(); }
    }, [apply]);
    const logout = useCallback(async () => {
        setLogoutRequested(false);
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
    useEffect(() => {
        if (!isLoading && !user && !publicPage && !sessionError) {
            const next = window.location.pathname + window.location.search;
            router.replace(`/auth/login?next=${encodeURIComponent(next)}`);
        }
    }, [isLoading, user, publicPage, sessionError, router]);
    return <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, sessionError, isCompletingSignIn, login, register, logout, requestLogout, reloadSession }}>
        <div className="signin-transition-content" data-stage={stage} inert={isCompletingSignIn} aria-busy={isCompletingSignIn}>
        {isLoading ? <div role="status" style={{ padding: "32px", color: "var(--text-secondary)" }}>Loading Corten…</div> :
            !user && (!publicPage || (sessionError && pendingLogout())) ? <div className="account-settings" role={sessionError ? "alert" : "status"}><p>{sessionError || "Taking you to sign in…"}</p>{sessionError && <button className="auth-submit" onClick={() => void reloadSession()}>Retry connection</button>}</div> :
            <div key={user?.id || "guest"} style={{ display: "contents" }}>{children}</div>}
        </div>
        {isCompletingSignIn && <>
            <div className="signin-transition-cover" data-stage={stage} aria-hidden="true" />
            <span className="sr-only" role="status">Signed in</span>
        </>}
        {user && logoutRequested && <SignOutDialog onCancel={() => setLogoutRequested(false)} onConfirm={() => void logout()} />}
    </AuthContext.Provider>;
}
export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) throw new Error("useAuth must be used inside AuthProvider");
    return context;
}
