"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
    Search, Plus, MoreHorizontal, Pencil, Trash2, LayoutGrid, MessageSquare, FileText, Users,
    ScrollText, Upload, UserPlus, LogOut, RefreshCw, Loader2, Inbox,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { spacesApi, relativeTime, canEdit, type PendingInvitation, type Space, type SpaceFields } from "@/lib/spacesApi";
import { clearLegacyBrowserSpaces, legacyBrowserSpaces } from "@/lib/spaces";
import SpaceFormModal from "@/components/spaces/SpaceFormModal";
import { RoleBadge, SpaceIcon } from "@/components/spaces/SpaceVisuals";
import RemoveSpaceDialog from "@/components/spaces/RemoveSpaceDialog";

type Filter = "all" | "owned" | "shared";

export default function SpacesPage() {
    const { user } = useAuth();
    const router = useRouter();
    const [spaces, setSpaces] = useState<Space[] | null>(null);
    const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [query, setQuery] = useState("");
    const [filter, setFilter] = useState<Filter>("all");
    const [creating, setCreating] = useState(false);
    const [editing, setEditing] = useState<Space | null>(null);
    const [menu, setMenu] = useState<string | null>(null);
    const [pendingRemoval, setPendingRemoval] = useState<{ space: Space; leave: boolean } | null>(null);
    const [respondId, setRespondId] = useState("");

    const load = useCallback(async () => {
        try {
            const [list, pending] = await Promise.all([spacesApi.list(), spacesApi.invitations().catch(() => [])]);
            setSpaces(list);
            setInvitations(pending);
            setError("");
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "Spaces could not be loaded.");
        }
    }, []);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            // Spaces from the earlier browser-only design move into the account once.
            const legacy = legacyBrowserSpaces();
            if (legacy.length) {
                try {
                    const result = await spacesApi.importLegacy(legacy);
                    clearLegacyBrowserSpaces([...Object.keys(result.imported), ...((result as { skipped?: string[] }).skipped ?? [])]);
                    if (!cancelled && Object.keys(result.imported).length) setNotice("Spaces saved on this device are now stored in your account.");
                } catch { /* The local copy stays until a later visit succeeds. */ }
            }
            if (!cancelled) await load();
        })();
        const refresh = () => { if (document.visibilityState === "visible") void load(); };
        document.addEventListener("visibilitychange", refresh);
        return () => { cancelled = true; document.removeEventListener("visibilitychange", refresh); };
    }, [load]);

    useEffect(() => {
        if (!menu) return;
        const close = () => setMenu(null);
        const key = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(null); };
        window.addEventListener("click", close);
        window.addEventListener("keydown", key);
        return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", key); };
    }, [menu]);

    const counts = useMemo(() => ({
        all: spaces?.length ?? 0,
        owned: spaces?.filter(space => space.role === "owner").length ?? 0,
        shared: spaces?.filter(space => space.role !== "owner").length ?? 0,
    }), [spaces]);

    const visible = useMemo(() => {
        const text = query.trim().toLowerCase();
        return (spaces ?? []).filter(space =>
            (filter === "all" || (filter === "owned" ? space.role === "owner" : space.role !== "owner")) &&
            (!text || space.name.toLowerCase().includes(text) || space.description.toLowerCase().includes(text)));
    }, [spaces, query, filter]);

    const create = async (fields: SpaceFields & { name: string }) => {
        const space = await spacesApi.create(fields);
        setCreating(false);
        router.push(`/spaces/${space.id}`);
    };
    const saveDetails = async (fields: SpaceFields & { name: string }) => {
        if (!editing) return;
        const updated = await spacesApi.update(editing, fields);
        setSpaces(current => current?.map(space => space.id === updated.id ? updated : space) ?? null);
        setEditing(null);
    };
    const respond = async (invitation: PendingInvitation, accept: boolean) => {
        setRespondId(invitation.id);
        try {
            const result = await spacesApi.respond(invitation.id, accept);
            if (accept && result?.spaceId) { router.push(`/spaces/${result.spaceId}`); return; }
            await load();
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "The invitation could not be updated.");
        } finally { setRespondId(""); }
    };

    return (
        <div className="sp-spaces-page sx-home">
            <header className="sp-spaces-header sx-home-header">
                <div className="sx-home-title">
                    <h1 className="sp-spaces-title">Spaces</h1>
                    <p className="sx-muted">Shared workspaces with their own instructions, files and team</p>
                </div>
                <div className="sp-spaces-search-wrap">
                    <Search size={15} className="sp-spaces-search-icon" aria-hidden="true" />
                    <input type="search" className="sp-spaces-search" placeholder="Search Spaces" value={query}
                        aria-label="Search Spaces" onChange={event => setQuery(event.target.value)} />
                </div>
                <div className="sp-spaces-header-actions">
                    <Link href="/spaces/templates" className="sp-spaces-tpl-btn"><LayoutGrid size={14} /><span>Templates</span></Link>
                    <button className="sp-spaces-create-btn" onClick={() => setCreating(true)}><Plus size={16} /><span>New Space</span></button>
                </div>
            </header>

            <main className="sp-spaces-body sx-home-body">
                {notice && <div className="sx-banner sx-banner--info" role="status">{notice}<button className="sx-banner-close" aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}

                {invitations.length > 0 && (
                    <section className="sx-invitations" aria-labelledby="invitations-heading">
                        <h2 id="invitations-heading" className="sx-section-title"><Inbox size={14} aria-hidden="true" /> Invitations <span className="sx-count">{invitations.length}</span></h2>
                        <ul>
                            {invitations.map(invitation => (
                                <li key={invitation.id} className="sx-invitation">
                                    <SpaceIcon icon={invitation.icon} color={invitation.color} size={18} box={38} />
                                    <div className="sx-invitation-text">
                                        <strong>{invitation.spaceName}</strong>
                                        <span className="sx-muted">{invitation.inviterName} invited you · <RoleBadge role={invitation.role} /></span>
                                    </div>
                                    <div className="sx-invitation-actions">
                                        <button className="sx-btn sx-btn--ghost" disabled={respondId === invitation.id} onClick={() => void respond(invitation, false)}>Decline</button>
                                        <button className="sx-btn sx-btn--primary" disabled={respondId === invitation.id} onClick={() => void respond(invitation, true)}>
                                            {respondId === invitation.id && <Loader2 size={14} className="sx-spin" />} Join Space
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    </section>
                )}

                {error && (
                    <div className="sx-banner sx-banner--error" role="alert">
                        <span>{error}</span>
                        <button className="sx-btn sx-btn--secondary" onClick={() => { setError(""); void load(); }}><RefreshCw size={14} /> Retry</button>
                    </div>
                )}

                {spaces === null && !error ? (
                    <div className="sp-spaces-grid" aria-busy="true" aria-label="Loading Spaces">
                        {[0, 1, 2, 3].map(i => <div key={i} className="sx-skeleton sx-skeleton--card" />)}
                    </div>
                ) : spaces && spaces.length === 0 ? (
                    <section className="sx-empty-hero">
                        <h2>Create a home for your team&apos;s research</h2>
                        <p className="sx-muted">A Space keeps related questions together and answers them with the context you give it.</p>
                        <ul className="sx-value-props">
                            <li><ScrollText size={18} aria-hidden="true" /><div><strong>Custom instructions</strong><span>Set the tone, format and focus for every answer.</span></div></li>
                            <li><Upload size={18} aria-hidden="true" /><div><strong>Your files as sources</strong><span>Answers cite uploaded PDFs, Office files and notes.</span></div></li>
                            <li><UserPlus size={18} aria-hidden="true" /><div><strong>Built for teams</strong><span>Invite colleagues as editors or viewers.</span></div></li>
                        </ul>
                        <div className="sx-empty-actions">
                            <button className="sp-spaces-create-btn" onClick={() => setCreating(true)}><Plus size={16} /> Create a Space</button>
                            <Link href="/spaces/templates" className="sp-spaces-tpl-btn"><LayoutGrid size={14} /> Start from a template</Link>
                        </div>
                    </section>
                ) : spaces && (
                    <>
                        <div className="sx-tabs" role="tablist" aria-label="Filter Spaces">
                            {([["all", "All"], ["owned", "Owned by me"], ["shared", "Shared with me"]] as [Filter, string][]).map(([key, label]) => (
                                <button key={key} role="tab" aria-selected={filter === key} className={`sx-tab ${filter === key ? "active" : ""}`}
                                    onClick={() => setFilter(key)}>{label} <span className="sx-count">{counts[key]}</span></button>
                            ))}
                        </div>
                        <div className="sp-spaces-grid">
                            {visible.map(space => (
                                <div key={space.id} className="sp-space-card-wrap">
                                    <Link href={`/spaces/${space.id}`} className="sp-space-card sx-card">
                                        <div className="sx-card-top">
                                            <SpaceIcon icon={space.icon} color={space.color} size={22} box={44} />
                                            <RoleBadge role={space.role} />
                                        </div>
                                        <div className="sp-space-card-body">
                                            <h3 className="sp-space-card-name">{space.name}</h3>
                                            <p className="sp-space-card-desc">{space.description || (space.role === "owner" ? "No description" : `Shared by ${space.ownerName ?? "a teammate"}`)}</p>
                                        </div>
                                        <div className="sp-space-card-footer">
                                            <div className="sp-space-card-stats">
                                                <span title="Threads"><MessageSquare size={11} aria-hidden="true" /> {space.threadCount}</span>
                                                <span title="Files"><FileText size={11} aria-hidden="true" /> {space.fileCount}</span>
                                                <span title="Members"><Users size={11} aria-hidden="true" /> {space.memberCount}</span>
                                            </div>
                                            <span className="sp-space-card-date">{relativeTime(space.updatedAt)}</span>
                                        </div>
                                    </Link>
                                    <button className="sp-space-card-menu sx-card-menu" aria-label={`Actions for ${space.name}`} aria-haspopup="menu"
                                        aria-expanded={menu === space.id}
                                        onClick={event => { event.preventDefault(); event.stopPropagation(); setMenu(menu === space.id ? null : space.id); }}>
                                        <MoreHorizontal size={16} />
                                    </button>
                                    {menu === space.id && (
                                        <div className="sp-space-ctx" role="menu" onClick={event => event.stopPropagation()}>
                                            {canEdit(space.role) && (
                                                <button role="menuitem" className="sp-space-ctx-item" onClick={() => { setEditing(space); setMenu(null); }}><Pencil size={13} /> Edit details</button>
                                            )}
                                            {space.role !== "owner" && (
                                                <button role="menuitem" className="sp-space-ctx-item sp-space-ctx-danger" onClick={() => { setPendingRemoval({ space, leave: true }); setMenu(null); }}><LogOut size={13} /> Leave Space</button>
                                            )}
                                            {space.role === "owner" && (<>
                                                <div className="sp-space-ctx-divider" />
                                                <button role="menuitem" className="sp-space-ctx-item sp-space-ctx-danger" onClick={() => { setPendingRemoval({ space, leave: false }); setMenu(null); }}><Trash2 size={13} /> Delete Space</button>
                                            </>)}
                                        </div>
                                    )}
                                </div>
                            ))}
                            {filter !== "shared" && !query && (
                                <button className="sp-space-card sp-space-card--add" onClick={() => setCreating(true)}><Plus size={24} strokeWidth={1.5} /><span>New Space</span></button>
                            )}
                        </div>
                        {visible.length === 0 && (
                            <p className="sp-spaces-no-results">{query ? <>No Spaces match &ldquo;{query}&rdquo;</> : filter === "shared" ? "No one has shared a Space with you yet." : "You don't own any Spaces yet."}</p>
                        )}
                    </>
                )}
            </main>

            {(creating || editing) && (
                <SpaceFormModal initial={editing ?? undefined} onSubmit={editing ? saveDetails : create}
                    onClose={() => { setCreating(false); setEditing(null); }} />
            )}
            {pendingRemoval && user && (
                <RemoveSpaceDialog {...pendingRemoval} userId={user.id} onClose={() => setPendingRemoval(null)}
                    onDone={() => { setPendingRemoval(null); void load(); }} />
            )}
        </div>
    );
}
