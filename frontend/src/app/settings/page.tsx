"use client";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";
import { api } from "@/lib/api";
import CloudSyncStatus from "@/components/layout/CloudSyncStatus";
import PersonalizationSettings from "@/components/settings/PersonalizationSettings";
import { Brain, Check, Database, FileText, Loader2, LogOut, SlidersHorizontal, UserRound } from "lucide-react";
import "@/styles/settings.css";

const SECTIONS = [
    { id: "profile", label: "Profile", icon: UserRound },
    { id: "responses", label: "Responses", icon: SlidersHorizontal },
    { id: "memory", label: "Memory", icon: Brain },
    { id: "files", label: "Files", icon: FileText },
    { id: "data", label: "Data & sync", icon: Database },
] as const;
type Section = typeof SECTIONS[number]["id"];

export default function SettingsPage() {
    const { user, logout, sessionError, reloadSession } = useAuth();
    const [active, setActive] = useState<Section>("profile");
    const [opened, setOpened] = useState(false);
    const [name, setName] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState("");
    const [failed, setFailed] = useState(false);
    const [signingOut, setSigningOut] = useState(false);
    const draftName = (name ?? user?.name ?? "").trim();
    const select = (section: Section) => {
        setActive(section);
        if (["responses", "memory", "files"].includes(section)) setOpened(true);
    };
    const save = async (event: React.FormEvent) => {
        event.preventDefault();
        if (saving || draftName.length < 2 || !user || draftName === user.name) return;
        setSaving(true); setMessage(""); setFailed(false);
        try { await api.put("/api/v1/users/me", { name: draftName }); await reloadSession(); setMessage("Profile updated."); }
        catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : "Unable to save. Please try again."); }
        finally { setSaving(false); }
    };
    return <div className="settings-page">
        <header className="settings-header"><h1>Settings</h1>{user && <div className="settings-identity"><span className="settings-avatar" aria-hidden="true">{user.name.trim().slice(0, 1).toUpperCase()}</span><span title={user.email}>{user.name}</span></div>}</header>
        {sessionError && <div className="settings-message settings-message-error" role="alert">{sessionError}<button className="settings-button" onClick={() => void reloadSession()}>Retry</button></div>}
        <div className="settings-layout">
            <nav className="settings-nav" role="tablist" aria-label="Settings sections" onKeyDown={event => {
                if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const index = SECTIONS.findIndex(section => section.id === active);
                const next = event.key === "Home" ? 0 : event.key === "End" ? SECTIONS.length - 1 : (index + (["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1) + SECTIONS.length) % SECTIONS.length;
                select(SECTIONS[next].id);
                document.getElementById(`settings-tab-${SECTIONS[next].id}`)?.focus();
            }}>{SECTIONS.map(({ id, label, icon: Icon }) => <button key={id} id={`settings-tab-${id}`} role="tab" aria-selected={active === id} aria-controls={`settings-panel-${id}`} tabIndex={active === id ? 0 : -1} onClick={() => select(id)}><Icon size={17} strokeWidth={1.6} aria-hidden="true" />{label}</button>)}</nav>
            <div className="settings-content">
                <section className="settings-panel" id="settings-panel-profile" role="tabpanel" aria-labelledby="settings-tab-profile" tabIndex={0} hidden={active !== "profile"}>
                    <div className="settings-panel-heading"><h2>Profile</h2>{user && <span className="settings-plan">{user.subscription_tier}</span>}</div>
                    {user ? <>
                        <form onSubmit={save} className="settings-profile-form">
                            <label htmlFor="profile-name">Display name</label>
                            <input className="settings-input" id="profile-name" value={name ?? user.name} onChange={event => { setName(event.target.value); setMessage(""); }} minLength={2} maxLength={100} required autoComplete="name" disabled={saving} />
                            <div className="settings-form-footer"><span className="settings-message" role={failed ? "alert" : "status"}>{message && <>{!failed && <Check size={14} aria-hidden="true" />}{message}</>}</span><button className="settings-button settings-button-primary" disabled={saving || draftName.length < 2 || draftName === user.name}>{saving && <Loader2 size={14} className="sx-spin" aria-hidden="true" />}{saving ? "Saving…" : "Save changes"}</button></div>
                        </form>
                        <dl className="settings-account-details"><div><dt>Email</dt><dd>{user.email}</dd></div></dl>
                        <div className="settings-action-row"><span>Password</span><Link className="settings-button" href="/auth/forgot-password">Reset password</Link></div>
                        <div className="settings-action-row"><span>Session</span><button className="settings-button" disabled={signingOut} onClick={async () => { setSigningOut(true); try { await logout(); } finally { setSigningOut(false); } }}><LogOut size={14} aria-hidden="true" />{signingOut ? "Signing out…" : "Sign out"}</button></div>
                    </> : <Link className="settings-button" href="/auth/login?next=%2Fsettings">Sign in</Link>}
                </section>
                {user && <>
                    <div hidden={active === "profile" || active === "data"}>{opened ? <PersonalizationSettings section={active === "memory" || active === "files" ? active : "responses"} /> : ["responses", "memory", "files"].map(id => <section key={id} id={`settings-panel-${id}`} role="tabpanel" aria-labelledby={`settings-tab-${id}`} hidden />)}</div>
                    <section className="settings-panel" id="settings-panel-data" role="tabpanel" aria-labelledby="settings-tab-data" tabIndex={0} hidden={active !== "data"}>
                        <div className="settings-panel-heading"><h2>Data & sync</h2></div>
                        <div className="settings-sync"><Database size={18} aria-hidden="true" /><CloudSyncStatus /></div>
                        <dl className="settings-data-details"><div><dt>History, Spaces & preferences</dt><dd>Account storage</dd></div><div><dt>Chat files</dt><dd>Retained for 90 days</dd></div><div><dt>Analyst uploads</dt><dd>Current session only</dd></div></dl>
                    </section>
                </>}
            </div>
        </div>
    </div>;
}
