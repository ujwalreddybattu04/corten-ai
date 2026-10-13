"use client";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";
import { api } from "@/lib/api";
import CloudSyncStatus from "@/components/layout/CloudSyncStatus";
import PersonalizationSettings from "@/components/settings/PersonalizationSettings";

export default function SettingsPage() {
    const { user, logout, sessionError, reloadSession } = useAuth();
    const [name, setName] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState("");
    const save = async (event: React.FormEvent) => {
        event.preventDefault();
        setSaving(true); setMessage("");
        try { await api.put("/api/v1/users/me", { name: (name ?? user?.name ?? "").trim() }); await reloadSession(); setMessage("Profile updated."); }
        catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save. Please try again."); }
        finally { setSaving(false); }
    };
    return <div className="account-settings">
        <h1>Account settings</h1>
        <p className="account-description">Manage your Corten session.</p>
        {sessionError && <div className="auth-error-banner" role="alert">{sessionError}<button onClick={() => void reloadSession()}>Retry</button></div>}
        <section className="account-panel">
            <h2>{user ? "Your account" : "Sign in to Corten"}</h2>
            {user ? <><dl><dt>Email</dt><dd>{user.email}</dd><dt>Plan</dt><dd>{user.subscription_tier}</dd></dl>
                <form onSubmit={save} style={{ marginBottom: 24 }}>
                    <label htmlFor="profile-name">Display name</label>
                    <input className="auth-input" id="profile-name" value={name ?? user.name} onChange={event => setName(event.target.value)} minLength={2} maxLength={100} required autoComplete="name" disabled={saving} />
                    <button className="auth-submit" disabled={saving || (name ?? user.name).trim() === user.name}>{saving ? "Saving…" : "Save profile"}</button>
                </form>
                {message && <p role="status">{message}</p>}
                <CloudSyncStatus />
                <button className="auth-submit" onClick={() => void logout()}>Sign out</button></> :
                <><p>Use your email and password to access your account.</p><Link className="auth-submit" href="/auth/login?next=%2Fsettings">Sign in</Link><p><Link href="/auth/signup?next=%2Fsettings">Create an account</Link></p></>}
        </section>
        {user && <PersonalizationSettings />}
        <p className="account-description">Signed-in chat history, Spaces and Discover preferences sync to your personal account. Guest work stays in this browser. Uploaded analyst files are processed for the current session; keep your exported results.</p>
    </div>;
}
