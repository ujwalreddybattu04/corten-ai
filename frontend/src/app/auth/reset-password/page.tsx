"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Eye, EyeOff, LockKeyhole, LoaderCircle } from "lucide-react";
import { api, invalidateSessionRequests } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export default function ResetPassword() {
    const [token, setToken] = useState<string | null>(null);
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [show, setShow] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [complete, setComplete] = useState(false);
    const { reloadSession } = useAuth();
    useEffect(() => {
        const readLink = () => {
            setComplete(new URLSearchParams(window.location.search).get("complete") === "1");
            const value = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
            setToken(/^[A-Za-z0-9_-]{43}$/.test(value) ? value : "");
            setError(""); setPassword(""); setConfirm("");
        };
        readLink();
        window.addEventListener("hashchange", readLink);
        window.addEventListener("popstate", readLink);
        return () => { window.removeEventListener("hashchange", readLink); window.removeEventListener("popstate", readLink); };
    }, []);
    async function submit(event: React.FormEvent) {
        event.preventDefault(); if (busy || !token) return;
        if (password !== confirm) { setError("Your passwords don't match."); return; }
        setBusy(true); setError("");
        try {
            await api.post("/api/v1/auth/reset-password", { token, password });
            window.history.replaceState(null, "", "/auth/reset-password?complete=1");
            setToken(""); setPassword(""); setConfirm(""); setComplete(true);
            invalidateSessionRequests(); await reloadSession();
        } catch (error) { setError(error instanceof Error ? error.message : "Unable to reset your password. Please retry."); }
        finally { setBusy(false); }
    }
    return <div className="auth-shell"><div className="auth-card" role="main"><div className="auth-card-content">
        <div className="auth-brand"><div className="auth-brand-logo"><LockKeyhole size={24} aria-hidden="true" /></div><span className="auth-brand-name">Corten</span></div>
        <h1 className="auth-heading">{complete ? "You're ready to return" : "Choose a new password"}</h1>
        <p className="auth-subheading">{complete ? "Your password is updated. Sign in again on your devices using the new password." : "Use at least 8 characters and choose a password you haven't used elsewhere."}</p>
        {complete ? <div role="status"><CheckCircle2 size={32} style={{ marginBottom: 18, color: "#8ab9a8" }} /><Link className="auth-submit" href="/auth/login">Sign in to Corten</Link></div> : token === null ? <p role="status">Checking your reset link…</p> : !token ? <><div className="auth-error-banner" role="alert">This reset link is missing or invalid. Request a new link.</div><Link className="auth-submit" href="/auth/forgot-password">Request a new reset link</Link></> :
            <form className="auth-form" onSubmit={submit}>
                <div className="auth-field"><label className="auth-label" htmlFor="new-password">New password</label><div className="auth-input-wrapper"><input id="new-password" className="auth-input" type={show ? "text" : "password"} autoComplete="new-password" required minLength={8} maxLength={1024} value={password} onChange={event => setPassword(event.target.value)} disabled={busy} /><button className="auth-pw-toggle" type="button" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></div>
                <div className="auth-field"><label className="auth-label" htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" className="auth-input" type={show ? "text" : "password"} autoComplete="new-password" required minLength={8} maxLength={1024} value={confirm} onChange={event => setConfirm(event.target.value)} disabled={busy} /></div>
                {error && <div className="auth-error-banner" role="alert">{error}</div>}
                <button className="auth-submit" disabled={busy || password.length < 8 || !confirm}>{busy ? <><LoaderCircle size={16} /> Updating password…</> : "Update password"}</button>
            </form>}
        {!complete && <div className="auth-footer"><Link href="/auth/login">Back to sign in</Link></div>}
    </div></div></div>;
}
