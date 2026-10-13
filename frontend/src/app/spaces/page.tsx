"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, Plus, MoreHorizontal, Pencil, Trash2, LogOut, RefreshCw, Loader2, ArrowRight, Users } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { spacesApi, relativeTime, canEdit, ROLE_LABELS, type PendingInvitation, type Space, type SpaceFields } from "@/lib/spacesApi";
import { clearLegacyBrowserSpaces, legacyBrowserSpaces } from "@/lib/spaces";
import { FEATURED_TEMPLATES } from "@/lib/spaceTemplates";
import SpaceFormModal from "@/components/spaces/SpaceFormModal";
import { SpaceIcon } from "@/components/spaces/SpaceVisuals";
import RemoveSpaceDialog from "@/components/spaces/RemoveSpaceDialog";
import TemplateGrid from "@/components/spaces/TemplateGrid";

type Filter = "all" | "owned" | "shared";

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** One quiet line of what is in a Space and when it last changed. */
function spaceSummary(space: Space): string {
    const parts = [space.threadCount ? plural(space.threadCount, "thread") : "No threads yet"];
    if (space.fileCount) parts.push(plural(space.fileCount, "file"));
    parts.push(relativeTime(space.updatedAt));
    return parts.join(" · ");
}

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

    const empty = spaces !== null && spaces.length === 0;

    return (
        <div className="sv-page">
            <div className="sv-page-inner">
                <header className="sv-home-head">
                    <div>
                        <h1>Spaces</h1>
                        <p>Organize research by project. Each Space keeps its own instructions, files, threads and people.</p>
                    </div>
                    <button className="sx-btn sx-btn--primary sv-new" onClick={() => setCreating(true)}><Plus size={16} /> New Space</button>
                </header>

                {notice && <div className="sx-banner sx-banner--info" role="status">{notice}<button className="sx-banner-close" aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}
                {error && (
                    <div className="sx-banner sx-banner--error" role="alert">
                        <span>{error}</span>
                        <button className="sx-btn sx-btn--secondary sx-btn--sm" onClick={() => { setError(""); void load(); }}><RefreshCw size={13} /> Retry</button>
                    </div>
                )}

                {invitations.length > 0 && (
                    <section className="sv-invites" aria-labelledby="invitations-heading">
                        <h2 id="invitations-heading" className="sv-section-title">Invitations</h2>
                        {invitations.map(invitation => (
                            <div key={invitation.id} className="sv-invite">
                                <SpaceIcon icon={invitation.icon} size={36} />
                                <div className="sv-invite-text">
                                    <strong>{invitation.spaceName}</strong>
                                    <span>{invitation.inviterName} invited you · {ROLE_LABELS[invitation.role]}</span>
                                </div>
                                <button className="sx-btn sx-btn--ghost sx-btn--sm" disabled={respondId === invitation.id} onClick={() => void respond(invitation, false)}>Decline</button>
                                <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={respondId === invitation.id} onClick={() => void respond(invitation, true)}>
                                    {respondId === invitation.id && <Loader2 size={13} className="sx-spin" />} Join
                                </button>
                            </div>
                        ))}
                    </section>
                )}

                {spaces === null && !error ? (
                    <div className="sv-grid" aria-busy="true" aria-label="Loading Spaces">
                        {[0, 1, 2].map(i => <div key={i} className="sx-skeleton sv-skeleton-card" />)}
                    </div>
                ) : spaces && spaces.length > 0 && (
                    <section aria-label="Your Spaces">
                        <div className="sv-toolbar">
                            {counts.shared > 0 ? (
                                <div className="sv-segmented" role="tablist" aria-label="Filter Spaces">
                                    {([["all", "All"], ["owned", "Created by me"], ["shared", "Shared with me"]] as [Filter, string][]).map(([key, label]) => (
                                        <button key={key} role="tab" aria-selected={filter === key} className={filter === key ? "active" : ""}
                                            onClick={() => setFilter(key)}>{label}</button>
                                    ))}
                                </div>
                            ) : <h2 className="sv-section-title">Your Spaces</h2>}
                            {spaces.length > 3 && (
                                <label className="sv-search">
                                    <Search size={14} aria-hidden="true" />
                                    <input type="search" placeholder="Search Spaces" value={query} aria-label="Search Spaces"
                                        onChange={event => setQuery(event.target.value)} />
                                </label>
                            )}
                        </div>
                        <div className="sv-grid">
                            {visible.map(space => (
                                <div key={space.id} className="sv-card-wrap">
                                    <Link href={`/spaces/${space.id}`} className="sv-card">
                                        <SpaceIcon icon={space.icon} size={40} />
                                        <span className="sv-card-name">{space.name}</span>
                                        {(space.description || space.role !== "owner") && (
                                            <span className="sv-card-desc">{space.description || `Shared by ${space.ownerName ?? "a teammate"}`}</span>
                                        )}
                                        <span className="sv-card-meta">
                                            {space.memberCount > 1 && <span className="sv-card-people" title={plural(space.memberCount, "member")}><Users size={12} aria-hidden="true" /> {space.memberCount}</span>}
                                            {spaceSummary(space)}
                                        </span>
                                    </Link>
                                    <button className="sv-card-menu" aria-label={`Actions for ${space.name}`} aria-haspopup="menu"
                                        aria-expanded={menu === space.id}
                                        onClick={event => { event.preventDefault(); event.stopPropagation(); setMenu(menu === space.id ? null : space.id); }}>
                                        <MoreHorizontal size={16} />
                                    </button>
                                    {menu === space.id && (
                                        <div className="sv-menu" role="menu" onClick={event => event.stopPropagation()}>
                                            {canEdit(space.role) && <button role="menuitem" onClick={() => { setEditing(space); setMenu(null); }}><Pencil size={14} /> Edit details</button>}
                                            {space.role !== "owner"
                                                ? <button role="menuitem" className="danger" onClick={() => { setPendingRemoval({ space, leave: true }); setMenu(null); }}><LogOut size={14} /> Leave Space</button>
                                                : <button role="menuitem" className="danger" onClick={() => { setPendingRemoval({ space, leave: false }); setMenu(null); }}><Trash2 size={14} /> Delete Space</button>}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                        {visible.length === 0 && (
                            <p className="sv-no-results">{query ? <>No Spaces match &ldquo;{query}&rdquo;.</> : filter === "shared" ? "No one has shared a Space with you yet." : "You haven't created a Space yet."}</p>
                        )}
                    </section>
                )}

                <section className={`sv-templates ${empty ? "sv-templates--lead" : ""}`} aria-labelledby="templates-heading">
                    <div className="sv-toolbar">
                        <h2 id="templates-heading" className="sv-section-title">{empty ? "Start with a template" : "Templates"}</h2>
                        <Link href="/spaces/templates" className="sv-text-link">All templates <ArrowRight size={13} /></Link>
                    </div>
                    <TemplateGrid templates={FEATURED_TEMPLATES} />
                </section>
            </div>

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
