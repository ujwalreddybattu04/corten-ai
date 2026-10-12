"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
    ChevronRight, ArrowUp, Users, Pencil, MoreHorizontal, Trash2, LogOut, MessageSquare, ScrollText, FileText,
    Link2, Globe, Upload, Download, X, Plus, Check, Loader2, Eye, RefreshCw, FolderOpen, AlertCircle, Lock, ExternalLink,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { questionPath } from "@/lib/questionDrafts";
import { ApiRequestError } from "@/lib/api";
import {
    spacesApi, uploadSpaceFile, canEdit, relativeTime, formatBytes, normalizeLink, linkHost,
    ACCEPTED_FILES, MAX_FILE_BYTES, type Space, type SpaceFields, type SpaceFile, type SpaceThreadSummary,
} from "@/lib/spacesApi";
import { PersonAvatar, RoleBadge, SpaceIcon } from "@/components/spaces/SpaceVisuals";
import SpaceFormModal from "@/components/spaces/SpaceFormModal";
import ShareDialog from "@/components/spaces/ShareDialog";
import RemoveSpaceDialog from "@/components/spaces/RemoveSpaceDialog";

const INSTRUCTIONS_LIMIT = 8000;
const EXTENSIONS = new Set(ACCEPTED_FILES.split(","));

interface UploadItem { key: string; name: string; size: number; progress: number; status: "queued" | "uploading" | "failed"; error?: string; retryable?: boolean; file: File }

export default function SpaceDetailPage() {
    const { user } = useAuth();
    const router = useRouter();
    const spaceId = String(useParams().id ?? "");
    const [space, setSpace] = useState<Space | null>(null);
    const [threads, setThreads] = useState<SpaceThreadSummary[]>([]);
    const [nextThreads, setNextThreads] = useState<number | null>(null);
    const [files, setFiles] = useState<SpaceFile[]>([]);
    const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");
    const [loadError, setLoadError] = useState("");
    const [notice, setNotice] = useState("");
    const [dialog, setDialog] = useState<"" | "share" | "details" | "delete" | "leave">("");
    const [menuOpen, setMenuOpen] = useState(false);

    const load = useCallback(() => Promise.all([spacesApi.get(spaceId), spacesApi.threads(spaceId), spacesApi.files(spaceId)])
        .then(([detail, threadPage, fileList]) => {
            setSpace(detail);
            setThreads(threadPage.items);
            setNextThreads(threadPage.next);
            setFiles(fileList);
            setState("ready");
        }, failure => {
            if (failure instanceof ApiRequestError && failure.status === 404) { setState("missing"); return; }
            setLoadError(failure instanceof Error ? failure.message : "This Space could not be loaded.");
            setState(current => current === "ready" ? "ready" : "error");
        }), [spaceId]);

    useEffect(() => {
        void load();
        // Collaborators change Spaces too; refresh when the tab becomes active again.
        const refresh = () => { if (document.visibilityState === "visible") void load(); };
        document.addEventListener("visibilitychange", refresh);
        return () => document.removeEventListener("visibilitychange", refresh);
    }, [load]);

    useEffect(() => {
        if (!menuOpen) return;
        const close = () => setMenuOpen(false);
        const key = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
        window.addEventListener("click", close);
        window.addEventListener("keydown", key);
        return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", key); };
    }, [menuOpen]);

    /** Save context fields; on a concurrent edit, show the latest version and keep the user's draft. */
    const save = useCallback(async (fields: SpaceFields) => {
        if (!space) return;
        try {
            setSpace(await spacesApi.update(space, fields));
        } catch (failure) {
            if (failure instanceof ApiRequestError && failure.status === 409) {
                setSpace(await spacesApi.get(space.id));
                throw new Error("A teammate updated this Space a moment ago. The latest version is shown — review it and save again.");
            }
            throw failure;
        }
    }, [space]);

    if (state === "loading") {
        return <div className="sx-detail" aria-busy="true"><div className="sx-detail-inner">
            <div className="sx-skeleton sx-skeleton--title" /><div className="sx-skeleton sx-skeleton--composer" />
            <div className="sx-detail-grid"><div className="sx-skeleton sx-skeleton--panel" /><div className="sx-skeleton sx-skeleton--panel" /></div>
        </div></div>;
    }
    if (state === "missing") {
        return (
            <div className="sd-not-found">
                <div className="sd-not-found-icon"><FolderOpen size={48} strokeWidth={1} /></div>
                <h2>Space not available</h2>
                <p>It may have been deleted, or you no longer have access. Ask the owner for a new invitation.</p>
                <Link href="/spaces" className="sd-back-link">Back to Spaces</Link>
            </div>
        );
    }
    if (state === "error" || !space) {
        return (
            <div className="sd-not-found" role="alert">
                <div className="sd-not-found-icon"><AlertCircle size={44} strokeWidth={1.2} /></div>
                <h2>Couldn&apos;t open this Space</h2>
                <p>{loadError}</p>
                <button className="sx-btn sx-btn--secondary" onClick={() => { setState("loading"); void load(); }}><RefreshCw size={14} /> Retry</button>
            </div>
        );
    }

    const editable = canEdit(space.role);
    const owner = space.role === "owner";

    return (
        <div className="sx-detail">
            <div className="sx-detail-inner">
                <nav className="sd-breadcrumb" aria-label="Breadcrumb">
                    <Link href="/spaces" className="sd-breadcrumb-link">Spaces</Link>
                    <ChevronRight size={13} className="sd-breadcrumb-sep" aria-hidden="true" />
                    <span className="sd-breadcrumb-current" aria-current="page">{space.name}</span>
                </nav>

                <header className="sx-detail-header">
                    <SpaceIcon icon={space.icon} color={space.color} size={28} box={60} />
                    <div className="sx-detail-identity">
                        <h1>{space.name}</h1>
                        {space.description && <p className="sx-detail-description">{space.description}</p>}
                        <div className="sx-detail-meta">
                            <RoleBadge role={space.role} />
                            <span><Users size={12} aria-hidden="true" /> {space.memberCount} member{space.memberCount === 1 ? "" : "s"}</span>
                            {space.role !== "owner" && space.ownerName && <span>Owned by {space.ownerName}</span>}
                            <span>Updated {relativeTime(space.updatedAt).toLowerCase()}</span>
                        </div>
                    </div>
                    <div className="sx-detail-actions">
                        <button className="sx-btn sx-btn--primary" onClick={() => setDialog("share")}>
                            {owner ? <><Users size={14} /> Share</> : <><Users size={14} /> Members</>}
                        </button>
                        {editable && <button className="sx-btn sx-btn--secondary" onClick={() => setDialog("details")}><Pencil size={14} /> Edit</button>}
                        <div className="sx-menu-anchor">
                            <button className="sx-icon-btn" aria-label="More actions" aria-haspopup="menu" aria-expanded={menuOpen}
                                onClick={event => { event.stopPropagation(); setMenuOpen(!menuOpen); }}><MoreHorizontal size={16} /></button>
                            {menuOpen && (
                                <div className="sp-space-ctx sx-menu" role="menu" onClick={event => event.stopPropagation()}>
                                    {owner
                                        ? <button role="menuitem" className="sp-space-ctx-item sp-space-ctx-danger" onClick={() => { setDialog("delete"); setMenuOpen(false); }}><Trash2 size={13} /> Delete Space</button>
                                        : <button role="menuitem" className="sp-space-ctx-item sp-space-ctx-danger" onClick={() => { setDialog("leave"); setMenuOpen(false); }}><LogOut size={13} /> Leave Space</button>}
                                </div>
                            )}
                        </div>
                    </div>
                </header>

                {notice && <div className="sx-banner sx-banner--info" role="status">{notice}<button className="sx-banner-close" aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}

                {editable ? <Composer space={space} fileCount={files.length} /> : (
                    <div className="sx-banner sx-banner--muted"><Eye size={15} aria-hidden="true" /> You have view access. You can read threads, files and instructions. Ask the owner for edit access to ask questions here.</div>
                )}

                <div className="sx-detail-grid">
                    <main className="sx-detail-main">
                        <ThreadList space={space} threads={threads} next={nextThreads} userIsOwner={owner}
                            onMore={async () => {
                                const page = await spacesApi.threads(space.id, nextThreads);
                                setThreads(current => [...current, ...page.items.filter(item => !current.some(existing => existing.threadId === item.threadId))]);
                                setNextThreads(page.next);
                            }}
                            onRemoved={threadId => { setThreads(current => current.filter(item => item.threadId !== threadId)); setSpace({ ...space, threadCount: Math.max(0, space.threadCount - 1) }); }} />
                    </main>
                    <aside className="sx-detail-aside" aria-label="Space context">
                        <InstructionsCard space={space} editable={editable} onSave={save} />
                        <FilesCard space={space} files={files} editable={editable}
                            onFiles={update => setFiles(update)} onCount={count => setSpace(current => current ? { ...current, fileCount: count } : current)} />
                        <LinksCard space={space} editable={editable} onSave={save} />
                        <SourcesCard space={space} editable={editable} hasFiles={files.length > 0} onSave={save} />
                    </aside>
                </div>
            </div>

            {dialog === "share" && <ShareDialog space={space} onClose={() => setDialog("")} onChanged={() => void load()}
                onLeft={() => router.push("/spaces")} />}
            {dialog === "details" && <SpaceFormModal initial={space} onClose={() => setDialog("")}
                onSubmit={async fields => { await save(fields); setDialog(""); setNotice("Space details saved."); }} />}
            {(dialog === "delete" || dialog === "leave") && user && (
                <RemoveSpaceDialog space={space} leave={dialog === "leave"} userId={user.id} onClose={() => setDialog("")}
                    onDone={() => router.push("/spaces")} />
            )}
        </div>
    );
}

// ── Ask ──────────────────────────────────────────────────────────────────────

function Composer({ space, fileCount }: { space: Space; fileCount: number }) {
    const router = useRouter();
    const [query, setQuery] = useState("");
    const [error, setError] = useState("");
    const submit = (event?: React.FormEvent) => {
        event?.preventDefault();
        if (!query.trim()) return;
        try { router.push(questionPath(query, "all", space.id)); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to open this question."); }
    };
    const sources = space.webSearch ? (fileCount ? "Web and Space files" : "Web") : "Space files only";
    return (
        <form className="sx-composer" onSubmit={submit}>
            <label htmlFor="space-question" className="sx-visually-hidden">Ask a question in {space.name}</label>
            <textarea id="space-question" className="sx-composer-input" rows={2} maxLength={16000} value={query}
                placeholder={`Ask anything in ${space.name}…`} onChange={event => setQuery(event.target.value)}
                onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); } }} />
            <div className="sx-composer-footer">
                <div className="sx-composer-chips">
                    <span className="sx-chip">{space.webSearch ? <Globe size={12} aria-hidden="true" /> : <Lock size={12} aria-hidden="true" />} {sources}</span>
                    {space.instructions && <span className="sx-chip"><ScrollText size={12} aria-hidden="true" /> Instructions applied</span>}
                    {space.links.length > 0 && space.webSearch && <span className="sx-chip"><Link2 size={12} aria-hidden="true" /> {space.links.length} priority site{space.links.length === 1 ? "" : "s"}</span>}
                </div>
                <button type="submit" className="sx-composer-send" disabled={!query.trim()} aria-label="Ask"><ArrowUp size={16} /></button>
            </div>
            {error && <p className="sx-error" role="alert">{error}</p>}
        </form>
    );
}

// ── Threads ──────────────────────────────────────────────────────────────────

function ThreadList({ space, threads, next, userIsOwner, onMore, onRemoved }: {
    space: Space; threads: SpaceThreadSummary[]; next: number | null; userIsOwner: boolean;
    onMore: () => Promise<void>; onRemoved: (threadId: string) => void;
}) {
    const [loadingMore, setLoadingMore] = useState(false);
    const [removing, setRemoving] = useState("");
    const [confirming, setConfirming] = useState("");
    const [error, setError] = useState("");
    const remove = async (threadId: string) => {
        setRemoving(threadId);
        setError("");
        try { await spacesApi.removeThread(space.id, threadId); onRemoved(threadId); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "The thread could not be removed."); }
        finally { setRemoving(""); setConfirming(""); }
    };
    return (
        <section aria-labelledby="threads-heading">
            <h2 id="threads-heading" className="sx-section-title"><MessageSquare size={14} aria-hidden="true" /> Threads {threads.length > 0 && <span className="sx-count">{space.threadCount}</span>}</h2>
            {error && <p className="sx-error" role="alert">{error}</p>}
            {threads.length === 0 ? (
                <div className="sx-empty">
                    <MessageSquare size={22} aria-hidden="true" style={{ color: space.color }} />
                    <p>No threads yet</p>
                    <span>{canEdit(space.role) ? "Questions you ask here are saved for every member, with this Space's instructions and files applied." : "Threads that members ask here will appear in this list."}</span>
                </div>
            ) : (
                <ul className="sx-thread-list">
                    {threads.map(thread => (
                        <li key={thread.threadId} className="sx-thread">
                            <Link className="sx-thread-link" href={`/search?id=${encodeURIComponent(thread.threadId)}&space=${encodeURIComponent(space.id)}`}>
                                <span className="sx-thread-title">{thread.title}</span>
                                <span className="sx-thread-meta">
                                    <PersonAvatar name={thread.authorName} size={18} />
                                    {thread.isAuthor ? "You" : thread.authorName} · {relativeTime(thread.updatedAt)}
                                </span>
                            </Link>
                            {((thread.isAuthor && canEdit(space.role)) || userIsOwner) && (
                                confirming === thread.threadId ? (
                                    <span className="sx-inline-confirm">
                                        <button className="sx-btn sx-btn--danger sx-btn--sm" disabled={removing === thread.threadId} onClick={() => void remove(thread.threadId)}>
                                            {removing === thread.threadId ? <Loader2 size={12} className="sx-spin" /> : "Remove"}
                                        </button>
                                        <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => setConfirming("")}>Cancel</button>
                                    </span>
                                ) : (
                                    <button className="sx-icon-btn sx-thread-remove" aria-label={`Remove “${thread.title}” from this Space`} title="Remove from Space"
                                        onClick={() => setConfirming(thread.threadId)}><X size={14} /></button>
                                )
                            )}
                        </li>
                    ))}
                </ul>
            )}
            {next && (
                <button className="sx-btn sx-btn--secondary sx-load-more" disabled={loadingMore}
                    onClick={async () => { setLoadingMore(true); try { await onMore(); } catch { setError("More threads could not be loaded."); } finally { setLoadingMore(false); } }}>
                    {loadingMore && <Loader2 size={14} className="sx-spin" />} Show older threads
                </button>
            )}
        </section>
    );
}

// ── Instructions ─────────────────────────────────────────────────────────────

function InstructionsCard({ space, editable, onSave }: { space: Space; editable: boolean; onSave: (fields: SpaceFields) => Promise<void> }) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState(space.instructions);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const submit = async () => {
        setSaving(true);
        setError("");
        try { await onSave({ instructions: draft.trim() }); setEditing(false); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "Instructions could not be saved."); }
        finally { setSaving(false); }
    };
    return (
        <section className="sx-card-panel" aria-labelledby="instructions-heading">
            <div className="sx-panel-header">
                <h2 id="instructions-heading"><ScrollText size={14} aria-hidden="true" /> Instructions</h2>
                {editable && !editing && <button className="sx-link-btn" onClick={() => { setDraft(space.instructions); setEditing(true); }}>{space.instructions ? "Edit" : "Add"}</button>}
            </div>
            <p className="sx-panel-desc">Guidance the AI follows for every answer in this Space: role, tone, format and focus.</p>
            {editing ? (
                <div className="sx-instructions-edit">
                    <textarea className="sx-input" rows={7} maxLength={INSTRUCTIONS_LIMIT} autoFocus value={draft} aria-label="Space instructions"
                        placeholder="e.g. You are a pharmaceutical market analyst. Answer concisely, use tables for comparisons, and prefer regulator and company sources."
                        onChange={event => setDraft(event.target.value)} />
                    <div className="sx-instructions-footer">
                        <span className={`sx-counter ${draft.length > INSTRUCTIONS_LIMIT * 0.9 ? "sx-counter--warn" : ""}`}>{draft.length.toLocaleString()} / {INSTRUCTIONS_LIMIT.toLocaleString()}</span>
                        <div className="sx-row">
                            <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => { setEditing(false); setError(""); }} disabled={saving}>Cancel</button>
                            <button className="sx-btn sx-btn--primary sx-btn--sm" onClick={() => void submit()} disabled={saving}>
                                {saving && <Loader2 size={12} className="sx-spin" />} Save
                            </button>
                        </div>
                    </div>
                </div>
            ) : space.instructions ? (
                <p className="sx-instructions-text">{space.instructions}</p>
            ) : (
                <p className="sx-placeholder">{editable ? "No instructions yet. Answers use Corten's default style." : "No instructions have been added."}</p>
            )}
            {error && <p className="sx-error" role="alert">{error}</p>}
        </section>
    );
}

// ── Files ────────────────────────────────────────────────────────────────────

function fileProblem(file: File): string | null {
    const extension = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    if (!file.name.includes(".") || !EXTENSIONS.has(extension)) return "Unsupported type. Use PDF, Office, HTML or text files.";
    if (file.size > MAX_FILE_BYTES) return "Larger than 25 MB.";
    if (file.size === 0) return "This file is empty.";
    return null;
}

function FilesCard({ space, files, editable, onFiles, onCount }: {
    space: Space; files: SpaceFile[]; editable: boolean; onFiles: (files: SpaceFile[]) => void; onCount: (count: number) => void;
}) {
    const [uploads, setUploads] = useState<UploadItem[]>([]);
    const [dragging, setDragging] = useState(false);
    const [confirming, setConfirming] = useState("");
    const [error, setError] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);
    const filesRef = useRef(files);
    useEffect(() => { filesRef.current = files; }, [files]);
    const running = useRef(false);
    const queue = useRef<UploadItem[]>([]);
    const controller = useRef<AbortController | null>(null);
    useEffect(() => () => controller.current?.abort(), []);

    const patch = (key: string, changes: Partial<UploadItem>) => setUploads(current => current.map(item => item.key === key ? { ...item, ...changes } : item));
    const drain = async () => {
        if (running.current) return;
        running.current = true;
        controller.current = new AbortController();
        // One upload at a time keeps large files reliable on slower connections.
        while (queue.current.length) {
            const item = queue.current.shift()!;
            patch(item.key, { status: "uploading", progress: 0 });
            try {
                const saved = await uploadSpaceFile(space.id, item.file, progress => patch(item.key, { progress }), controller.current.signal);
                const next = [saved, ...filesRef.current];
                onFiles(next);
                onCount(next.length);
                setUploads(current => current.filter(entry => entry.key !== item.key));
            } catch (failure) {
                if (failure instanceof DOMException && failure.name === "AbortError") break;
                // Only connection and server failures can succeed on retry; duplicates or limits cannot.
                const status = failure instanceof ApiRequestError ? failure.status : 0;
                patch(item.key, { status: "failed", retryable: status === 0 || status === 401 || status === 429 || status >= 500,
                    error: failure instanceof Error ? failure.message : "Upload failed." });
            }
        }
        running.current = false;
    };
    const add = (list: FileList | File[]) => {
        const items: UploadItem[] = [...list].map(file => {
            const problem = fileProblem(file);
            return { key: crypto.randomUUID(), name: file.name, size: file.size, progress: 0, file,
                status: problem ? "failed" : "queued", error: problem ?? undefined };
        });
        setUploads(current => [...current, ...items]);
        queue.current.push(...items.filter(item => item.status === "queued"));
        void drain();
    };
    const retry = (item: UploadItem) => {
        if (fileProblem(item.file)) return;
        patch(item.key, { status: "queued", error: undefined, progress: 0 });
        queue.current.push(item);
        void drain();
    };
    const remove = async (file: SpaceFile) => {
        setError("");
        try {
            await spacesApi.removeFile(space.id, file.id);
            const next = filesRef.current.filter(item => item.id !== file.id);
            onFiles(next);
            onCount(next.length);
        } catch (failure) { setError(failure instanceof Error ? failure.message : "The file could not be removed."); }
        finally { setConfirming(""); }
    };

    return (
        <section className={`sx-card-panel ${dragging ? "sx-card-panel--drop" : ""}`} aria-labelledby="files-heading"
            onDragOver={event => { if (editable && event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
            onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
            onDrop={event => { if (!editable) return; event.preventDefault(); setDragging(false); add(event.dataTransfer.files); }}>
            <div className="sx-panel-header">
                <h2 id="files-heading"><FileText size={14} aria-hidden="true" /> Files {files.length > 0 && <span className="sx-count">{files.length}</span>}</h2>
                {editable && <button className="sx-link-btn" onClick={() => inputRef.current?.click()}>Upload</button>}
            </div>
            <p className="sx-panel-desc">Answers search these files and cite them alongside the web.</p>
            {editable && (
                <>
                    <input ref={inputRef} type="file" multiple accept={ACCEPTED_FILES} hidden
                        onChange={event => { if (event.target.files?.length) add(event.target.files); event.target.value = ""; }} />
                    <button type="button" className="sx-dropzone" onClick={() => inputRef.current?.click()}>
                        <Upload size={18} aria-hidden="true" />
                        <span><strong>Drop files here</strong> or browse</span>
                        <span className="sx-muted">PDF, Word, PowerPoint, Excel, HTML and text · up to 25 MB each</span>
                    </button>
                </>
            )}
            {uploads.length > 0 && (
                <ul className="sx-file-list" aria-label="Uploads">
                    {uploads.map(item => (
                        <li key={item.key} className={`sx-file sx-file--${item.status}`}>
                            <FileText size={16} aria-hidden="true" className="sx-file-icon" />
                            <div className="sx-file-text">
                                <span className="sx-file-name">{item.name}</span>
                                {item.status === "failed" ? <span className="sx-file-error" role="alert">{item.error}</span> : (
                                    <span className="sx-progress" role="progressbar" aria-label={`Uploading ${item.name}`} aria-valuemin={0} aria-valuemax={100}
                                        aria-valuenow={Math.round(item.progress * 100)}>
                                        <span style={{ width: `${Math.max(4, item.progress * 100)}%` }} />
                                    </span>
                                )}
                                {item.status === "uploading" && item.progress >= 1 && <span className="sx-muted">Reading and indexing…</span>}
                            </div>
                            {item.status === "failed" ? (
                                <span className="sx-row">
                                    {item.retryable && !fileProblem(item.file) && <button className="sx-link-btn" onClick={() => retry(item)}>Retry</button>}
                                    <button className="sx-icon-btn" aria-label={`Dismiss ${item.name}`} onClick={() => setUploads(current => current.filter(entry => entry.key !== item.key))}><X size={13} /></button>
                                </span>
                            ) : item.status === "queued" ? <span className="sx-muted">Waiting</span> : <Loader2 size={14} className="sx-spin" aria-hidden="true" />}
                        </li>
                    ))}
                </ul>
            )}
            {error && <p className="sx-error" role="alert">{error}</p>}
            {files.length > 0 ? (
                <ul className="sx-file-list">
                    {files.map(file => (
                        <li key={file.id} className="sx-file">
                            <FileText size={16} aria-hidden="true" className="sx-file-icon" />
                            <div className="sx-file-text">
                                <a className="sx-file-name" href={spacesApi.downloadUrl(space.id, file.id)} title={`Download ${file.name}`}>{file.name}</a>
                                <span className="sx-muted">{formatBytes(file.size)} · {file.uploadedBy ?? "Former member"} · {relativeTime(file.createdAt)}</span>
                            </div>
                            {confirming === file.id ? (
                                <span className="sx-inline-confirm">
                                    <button className="sx-btn sx-btn--danger sx-btn--sm" onClick={() => void remove(file)}>Remove</button>
                                    <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => setConfirming("")}>Cancel</button>
                                </span>
                            ) : (
                                <span className="sx-row sx-file-actions">
                                    <a className="sx-icon-btn" href={spacesApi.downloadUrl(space.id, file.id)} aria-label={`Download ${file.name}`}><Download size={13} /></a>
                                    {editable && <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Remove ${file.name}`} onClick={() => setConfirming(file.id)}><Trash2 size={13} /></button>}
                                </span>
                            )}
                        </li>
                    ))}
                </ul>
            ) : !editable && <p className="sx-placeholder">No files have been added.</p>}
        </section>
    );
}

// ── Links ────────────────────────────────────────────────────────────────────

function LinksCard({ space, editable, onSave }: { space: Space; editable: boolean; onSave: (fields: SpaceFields) => Promise<void> }) {
    const [adding, setAdding] = useState(false);
    const [value, setValue] = useState("");
    const [error, setError] = useState("");
    const [saving, setSaving] = useState(false);
    const update = async (links: string[]) => {
        setSaving(true);
        setError("");
        try { await onSave({ links }); return true; }
        catch (failure) { setError(failure instanceof Error ? failure.message : "Links could not be saved."); return false; }
        finally { setSaving(false); }
    };
    const add = async (event: React.FormEvent) => {
        event.preventDefault();
        const link = normalizeLink(value);
        if (!link) { setError("Enter a web address such as example.com or https://example.com/reports"); return; }
        if (space.links.includes(link)) { setValue(""); setAdding(false); return; }
        if (space.links.length >= 100) { setError("A Space can have up to 100 links."); return; }
        if (await update([...space.links, link])) { setValue(""); setAdding(false); }
    };
    return (
        <section className="sx-card-panel" aria-labelledby="links-heading">
            <div className="sx-panel-header">
                <h2 id="links-heading"><Link2 size={14} aria-hidden="true" /> Links {space.links.length > 0 && <span className="sx-count">{space.links.length}</span>}</h2>
                {editable && !adding && <button className="sx-link-btn" onClick={() => setAdding(true)}>Add</button>}
            </div>
            <p className="sx-panel-desc">Trusted sites searched first and cited ahead of the open web.</p>
            {space.links.length > 0 && (
                <ul className="sx-link-list">
                    {space.links.map(link => (
                        <li key={link} className="sx-link-item">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(linkHost(link))}&sz=32`} alt="" width={14} height={14}
                                onError={event => { (event.target as HTMLImageElement).style.visibility = "hidden"; }} />
                            <a href={link} target="_blank" rel="noopener noreferrer" className="sx-link-host" title={link}>{linkHost(link)}<ExternalLink size={10} aria-hidden="true" /></a>
                            {editable && <button className="sx-icon-btn" aria-label={`Remove ${linkHost(link)}`} disabled={saving}
                                onClick={() => void update(space.links.filter(item => item !== link))}><X size={12} /></button>}
                        </li>
                    ))}
                </ul>
            )}
            {adding && (
                <form className="sx-link-form" onSubmit={add}>
                    <input className="sx-input" autoFocus placeholder="example.com/reports" value={value} aria-label="Link to add" maxLength={2048}
                        onChange={event => { setValue(event.target.value); setError(""); }}
                        onKeyDown={event => { if (event.key === "Escape") { setAdding(false); setError(""); } }} />
                    <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={!value.trim() || saving} aria-label="Add link">
                        {saving ? <Loader2 size={12} className="sx-spin" /> : <Check size={13} />}
                    </button>
                </form>
            )}
            {!space.links.length && !adding && <p className="sx-placeholder">{editable ? <button className="sx-link-btn" onClick={() => setAdding(true)}><Plus size={12} /> Add a trusted site</button> : "No links have been added."}</p>}
            {error && <p className="sx-error" role="alert">{error}</p>}
        </section>
    );
}

// ── Sources ──────────────────────────────────────────────────────────────────

function SourcesCard({ space, editable, hasFiles, onSave }: { space: Space; editable: boolean; hasFiles: boolean; onSave: (fields: SpaceFields) => Promise<void> }) {
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const toggle = async () => {
        setSaving(true);
        setError("");
        try { await onSave({ webSearch: !space.webSearch }); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "The setting could not be saved."); }
        finally { setSaving(false); }
    };
    return (
        <section className="sx-card-panel" aria-labelledby="sources-heading">
            <div className="sx-panel-header"><h2 id="sources-heading"><Globe size={14} aria-hidden="true" /> Answer sources</h2></div>
            <div className="sx-switch-row">
                <div>
                    <span className="sx-switch-label" id="web-search-label">Search the web</span>
                    <span className="sx-panel-desc">{space.webSearch
                        ? "Answers combine web results with this Space's files."
                        : "Answers use only this Space's files. Nothing is searched on the web."}</span>
                </div>
                <button role="switch" aria-checked={space.webSearch} aria-labelledby="web-search-label" className="sx-switch"
                    disabled={!editable || saving} onClick={() => void toggle()}><span /></button>
            </div>
            {!space.webSearch && !hasFiles && <p className="sx-warning"><AlertCircle size={13} aria-hidden="true" /> Upload files so answers have something to draw on.</p>}
            {error && <p className="sx-error" role="alert">{error}</p>}
        </section>
    );
}
