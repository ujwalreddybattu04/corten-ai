"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, LoaderCircle, Mail, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";

export default function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [complete, setComplete] = useState(false);
    async function submit(event: React.FormEvent) {
        event.preventDefault(); if (busy) return;
        setError(""); setBusy(true);
        try { await api.post("/api/v1/auth/forgot-password", { email: email.trim() }); setComplete(true); }
        catch (error) { setError(error instanceof Error ? error.message : "Unable to request a reset. Please retry."); }
        finally { setBusy(false); }
    }
    return <div className="auth-shell"><div className="auth-card" role="main"><div className="auth-card-content">
        <div className="auth-brand"><div className="auth-brand-logo"><Mail size={24} aria-hidden="true" /></div><span className="auth-brand-name">Corten</span></div>
        <h1 className="auth-heading">{complete ? "Check your inbox" : "Forgot your password?"}</h1>
        <p className="auth-subheading">{complete ? "If an eligible account exists, we'll send a secure password reset link." : "Enter your account email and we'll help you get back to your workspace."}</p>
        {complete ? <div role="status"><CheckCircle2 size={32} style={{ marginBottom: 18, color: "#8ab9a8" }} /><p className="auth-subheading">The link expires in 30 minutes. Check Spam if it doesn't arrive. New requests replace older reset links.</p><button className="auth-submit" onClick={() => setComplete(false)}>Request another link</button></div> :
            <form className="auth-form" onSubmit={submit}>
                <div className="auth-field"><label className="auth-label" htmlFor="recovery-email">Email address</label><input id="recovery-email" className="auth-input" type="email" required autoComplete="email" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} disabled={busy} /></div>
                {error && <div className="auth-error-banner" role="alert">{error}</div>}
                <button className="auth-submit" disabled={busy || !email.trim()}>{busy ? <><LoaderCircle size={16} /> Requesting link…</> : "Send reset link"}</button>
            </form>}
        <div className="auth-footer"><Link href="/auth/login"><ArrowLeft size={14} /> Back to sign in</Link></div>
    </div></div></div>;
}
