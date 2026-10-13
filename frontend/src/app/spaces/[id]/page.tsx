"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
    ArrowLeft, ArrowUp, Users, Pencil, MoreHorizontal, Trash2, LogOut, FileText, Upload, Download, X, Plus, Loader2,
    RefreshCw, FolderOpen, AlertCircle, Lock, ExternalLink, UserPlus, Globe, Sparkles,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { questionPath } from "@/lib/questionDrafts";
import { ApiRequestError } from "@/lib/api";
import {
    spacesApi, uploadSpaceFile, canEdit, relativeTime, formatBytes, normalizeLink, linkHost, ROLE_LABELS,
    ACCEPTED_FILES, MAX_FILE_BYTES, type Space, type SpaceFields, type SpaceFile, type SpaceThreadSummary,
} from "@/lib/spacesApi";
import { starterQuestions } from "@/lib/spaceTemplates";
import { useAttachments } from "@/hooks/useAttachments";
import { AttachButton, AttachmentTray, ModeMenu, filesFromTransfer } from "@/components/chat/ComposerControls";
import { PersonAvatar, SpaceIcon } from "@/components/spaces/SpaceVisuals";
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
    const [draft, setDraft] = useState("");

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
        return <div className="sv-page" aria-busy="true"><div className="sv-page-inner">
            <div className="sx-skeleton sv-skeleton-head" /><div className="sx-skeleton sv-skeleton-composer" />
            <div className="sv-layout"><div className="sx-skeleton sv-skeleton-list" /><div className="sx-skeleton sv-skeleton-rail" /></div>
        </div></div>;
    }
    if (state === "missing" || state === "error" || !space) {
        const missing = state === "missing";
        return (
            <div className="sv-page"><div className="sv-state" role={missing ? undefined : "alert"}>
                {missing ? <FolderOpen size={40} strokeWidth={1.25} /> : <AlertCircle size={40} strokeWidth={1.25} />}
                <h1>{missing ? "This Space isn't available" : "Couldn't open this Space"}</h1>
                <p>{missing ? "It may have been deleted, or you no longer have access. Ask the owner to invite you again." : loadError}</p>
                {missing
                    ? <Link href="/spaces" className="sx-btn sx-btn--secondary">Back to Spaces</Link>
                    : <button className="sx-btn sx-btn--secondary" onClick={() => { setState("loading"); void load(); }}><RefreshCw size={14} /> Retry</button>}
            </div></div>
        );
    }

    const editable = canEdit(space.role);
    const owner = space.role === "owner";
    const access = owner
        ? (space.memberCount > 1 ? <><Users size={13} aria-hidden="true" /> Shared with {space.memberCount - 1} {space.memberCount === 2 ? "person" : "people"}</> : <><Lock size={13} aria-hidden="true" /> Private</>)
        : <><Users size={13} aria-hidden="true" /> {space.ownerName ? `${space.ownerName}'s Space` : "Shared Space"} · {ROLE_LABELS[space.role]}</>;

    return (
        <div className="sv-page">
            <div className="sv-page-inner">
                <Link href="/spaces" className="sv-back"><ArrowLeft size={15} /> Spaces</Link>

                <header className="sv-head">
                    <SpaceIcon icon={space.icon} size={56} />
                    <div className="sv-head-text">
                        <h1>{space.name}</h1>
                        {space.description && <p className="sv-head-desc">{space.description}</p>}
                        <p className="sv-head-meta">{access}</p>
                    </div>
                    <div className="sv-head-actions">
                        <button className="sx-btn sx-btn--secondary" onClick={() => setDialog("share")}>
                            {owner ? <><UserPlus size={15} /> Share</> : <><Users size={15} /> Members</>}
                        </button>
                        <div className="sv-menu-anchor">
                            <button className="sx-icon-btn sv-head-more" aria-label="More actions" aria-haspopup="menu" aria-expanded={menuOpen}
                                onClick={event => { event.stopPropagation(); setMenuOpen(!menuOpen); }}><MoreHorizontal size={18} /></button>
                            {menuOpen && (
                                <div className="sv-menu" role="menu" onClick={event => event.stopPropagation()}>
                                    {editable && <button role="menuitem" onClick={() => { setDialog("details"); setMenuOpen(false); }}><Pencil size={14} /> Edit details</button>}
                                    {owner
                                        ? <button role="menuitem" className="danger" onClick={() => { setDialog("delete"); setMenuOpen(false); }}><Trash2 size={14} /> Delete Space</button>
                                        : <button role="menuitem" className="danger" onClick={() => { setDialog("leave"); setMenuOpen(false); }}><LogOut size={14} /> Leave Space</button>}
                                </div>
                            )}
                        </div>
                    </div>
                </header>

                {notice && <div className="sx-banner sx-banner--info" role="status">{notice}<button className="sx-banner-close" aria-label="Dismiss" onClick={() => setNotice("")}>×</button></div>}

                <div className="sv-layout">
                    <main className="sv-main">
                        {editable ? <Composer space={space} fileCount={files.length} draft={draft} setDraft={setDraft} /> : (
                            <p className="sv-readonly"><Lock size={14} aria-hidden="true" /> You can read everything in this Space. Ask {space.ownerName ?? "the owner"} for edit access to ask questions here.</p>
                        )}
                        <ThreadList space={space} threads={threads} next={nextThreads} userIsOwner={owner} hasFiles={files.length > 0}
                            onSuggest={text => { setDraft(text); requestAnimationFrame(() => document.getElementById("space-question")?.focus()); }}
                            onMore={async () => {
                                const page = await spacesApi.threads(space.id, nextThreads);
                                setThreads(current => [...current, ...page.items.filter(item => !current.some(existing => existing.threadId === item.threadId))]);
                                setNextThreads(page.next);
                            }}
                            onRemoved={threadId => { setThreads(current => current.filter(item => item.threadId !== threadId)); setSpace({ ...space, threadCount: Math.max(0, space.threadCount - 1) }); }} />
                    </main>
                    <aside className="sv-rail" aria-label="Space context">
                        <AgentSection space={space} />
                        <InstructionsSection space={space} editable={editable} onSave={save} />
                        <FilesSection space={space} files={files} editable={editable}
                            onFiles={update => setFiles(update)} onCount={count => setSpace(current => current ? { ...current, fileCount: count } : current)} />
                        <LinksSection space={space} editable={editable} onSave={save} />
                        <SearchSection space={space} editable={editable} hasFiles={files.length > 0} onSave={save} />
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

function scopeLabel(space: Space, fileCount: number): string {
    const files = fileCount ? `${fileCount} file${fileCount === 1 ? "" : "s"}` : "";
    if (!space.webSearch) return files ? `${files} only` : "Space files only";
    return files ? `Web + ${files}` : "Web";
}

function Composer({ space, fileCount, draft, setDraft }: { space: Space; fileCount: number; draft: string; setDraft: (text: string) => void }) {
    const router = useRouter();
    const [error, setError] = useState("");
    const [dragging, setDragging] = useState(false);
    const attachments = useAttachments();
    const submit = (event?: React.FormEvent) => {
        event?.preventDefault();
        if (!draft.trim()) return;
        if (attachments.uploading) { setError("Wait for your files to finish uploading."); return; }
        try {
            router.push(questionPath(draft, "all", space.id, "search", attachments.ready));
            // The question now lives in its thread; coming back to the Space starts from an empty box.
            setDraft("");
        } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to open this question."); }
    };
    const scopeHint = space.webSearch
        ? `Answers search the web${fileCount ? " and this Space's files" : ""}${space.links.length ? `, checking ${space.links.length} priority site${space.links.length === 1 ? "" : "s"} first` : ""}.`
        : "Answers use only this Space's files.";
    return (
        <form className={`sv-composer ${dragging ? "sv-composer--drop" : ""}`} onSubmit={submit}
            onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
            onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
            onDrop={event => { const dropped = filesFromTransfer(event.dataTransfer); if (dropped.length) { event.preventDefault(); attachments.add(dropped); } setDragging(false); }}>
            <AttachmentTray items={attachments.items} onRemove={attachments.remove} />
            <label htmlFor="space-question" className="sx-visually-hidden">Ask a question in {space.name}</label>
            <textarea id="space-question" className="sv-composer-input" rows={2} maxLength={16000} value={draft}
                placeholder={`Ask anything in ${space.name}…`} onChange={event => setDraft(event.target.value)}
                onPaste={event => { const pasted = filesFromTransfer(event.clipboardData); if (pasted.length) { event.preventDefault(); attachments.add(pasted); } }}
                onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit(); } }} />
            <div className="sv-composer-bar">
                <span className="sv-scope" title={scopeHint}>
                    {space.webSearch ? <Globe size={13} aria-hidden="true" /> : <Lock size={13} aria-hidden="true" />}
                    {scopeLabel(space, fileCount)}
                    {space.instructions && <span className="sv-scope-extra">· Instructions on</span>}
                </span>
                <div className="sv-composer-actions">
                    <AttachButton onFiles={attachments.add} />
                    <ModeMenu />
                    <button type="submit" className="sv-send" disabled={!draft.trim() || attachments.uploading} aria-label="Ask"><ArrowUp size={17} /></button>
                </div>
            </div>
            {error && <p className="sx-error" role="alert">{error}</p>}
        </form>
    );
}

// ── Threads ──────────────────────────────────────────────────────────────────

function ThreadList({ space, threads, next, userIsOwner, hasFiles, onSuggest, onMore, onRemoved }: {
    space: Space; threads: SpaceThreadSummary[]; next: number | null; userIsOwner: boolean; hasFiles: boolean;
    onSuggest: (text: string) => void; onMore: () => Promise<void>; onRemoved: (threadId: string) => void;
}) {
    const [loadingMore, setLoadingMore] = useState(false);
    const [removing, setRemoving] = useState("");
    const [confirming, setConfirming] = useState("");
    const [error, setError] = useState("");
    const shared = space.memberCount > 1;
    const remove = async (threadId: string) => {
        setRemoving(threadId);
        setError("");
        try { await spacesApi.removeThread(space.id, threadId); onRemoved(threadId); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "The thread could not be removed."); }
        finally { setRemoving(""); setConfirming(""); }
    };
    const suggestions = starterQuestions(space, hasFiles);
    return (
        <section className="sv-threads" aria-labelledby="threads-heading">
            <h2 id="threads-heading" className="sv-section-title">Threads {threads.length > 0 && <span className="sv-count">{space.threadCount}</span>}</h2>
            {error && <p className="sx-error" role="alert">{error}</p>}
            {threads.length === 0 ? (
                canEdit(space.role) ? (
                    <div className="sv-start">
                        <p>Ask your first question. Every thread here is saved for the whole Space, with its instructions and files applied.</p>
                        <div className="sv-suggestions">
                            {suggestions.map(text => <button key={text} type="button" onClick={() => onSuggest(text)}>{text}</button>)}
                        </div>
                    </div>
                ) : <p className="sv-quiet">No one has asked a question in this Space yet.</p>
            ) : (
                <ul className="sv-thread-list">
                    {threads.map(thread => (
                        <li key={thread.threadId} className="sv-thread">
                            <Link className="sv-thread-link" href={`/search?id=${encodeURIComponent(thread.threadId)}&space=${encodeURIComponent(space.id)}`}>
                                <span className="sv-thread-title">{thread.question || thread.title}</span>
                                {thread.preview && <span className="sv-thread-preview">{thread.preview}</span>}
                                <span className="sv-thread-meta">
                                    {shared && <><PersonAvatar name={thread.authorName} size={18} /> {thread.isAuthor ? "You" : thread.authorName} · </>}
                                    {relativeTime(thread.updatedAt)}
                                </span>
                            </Link>
                            {((thread.isAuthor && canEdit(space.role)) || userIsOwner) && (
                                confirming === thread.threadId ? (
                                    <span className="sv-inline-confirm">
                                        <button className="sx-btn sx-btn--danger sx-btn--sm" disabled={removing === thread.threadId} onClick={() => void remove(thread.threadId)}>
                                            {removing === thread.threadId ? <Loader2 size={12} className="sx-spin" /> : "Remove"}
                                        </button>
                                        <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => setConfirming("")}>Cancel</button>
                                    </span>
                                ) : (
                                    <button className="sx-icon-btn sv-thread-remove" aria-label={`Remove “${thread.title}” from this Space`} title="Remove from Space"
                                        onClick={() => setConfirming(thread.threadId)}><X size={15} /></button>
                                )
                            )}
                        </li>
                    ))}
                </ul>
            )}
            {next && (
                <button className="sx-btn sx-btn--ghost sv-more" disabled={loadingMore}
                    onClick={async () => { setLoadingMore(true); try { await onMore(); } catch { setError("More threads could not be loaded."); } finally { setLoadingMore(false); } }}>
                    {loadingMore && <Loader2 size={14} className="sx-spin" />} Show older threads
                </button>
            )}
        </section>
    );
}

// ── Context rail ─────────────────────────────────────────────────────────────

function RailSection({ id, title, count, action, children, className = "", ...rest }: {
    id: string; title: string; count?: number; action?: React.ReactNode; children: React.ReactNode; className?: string;
} & React.HTMLAttributes<HTMLElement>) {
    return (
        <section className={`sv-rail-section ${className}`} aria-labelledby={id} {...rest}>
            <div className="sv-rail-head">
                <h2 id={id}>{title}{count ? <span className="sv-count">{count}</span> : null}</h2>
                {action}
            </div>
            {children}
        </section>
    );
}

/** The agent that answers here: the template that equips it and the tools it can call. */
function AgentSection({ space }: { space: Space }) {
    const agent = space.agent;
    if (!agent) return null;
    return (
        <RailSection id="agent-heading" title="Agent">
            <p className="sv-agent-name"><Sparkles size={14} aria-hidden="true" /> {agent.template ? `${agent.template.name} agent` : "Research agent"}</p>
            <p className="sv-agent-hint">Plans each answer, calls these tools for live data and charts, and cites every source.</p>
            {agent.tools.length > 0
                ? <ul className="sv-agent-tools" aria-label="Agent tools">{agent.tools.map(tool => <li key={tool.id} className="sv-tool-chip">{tool.label}</li>)}</ul>
                : <p className="sv-quiet">No tools: answers use only this Space&apos;s files.</p>}
        </RailSection>
    );
}

function InstructionsSection({ space, editable, onSave }: { space: Space; editable: boolean; onSave: (fields: SpaceFields) => Promise<void> }) {
    const [editing, setEditing] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const [draft, setDraft] = useState(space.instructions);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const long = space.instructions.length > 280 || space.instructions.split("\n").length > 5;
    const submit = async () => {
        setSaving(true);
        setError("");
        try { await onSave({ instructions: draft.trim() }); setEditing(false); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "Instructions could not be saved."); }
        finally { setSaving(false); }
    };
    const start = () => { setDraft(space.instructions); setEditing(true); };
    return (
        <RailSection id="instructions-heading" title="Instructions"
            action={editable && !editing && space.instructions ? <button className="sv-rail-action" onClick={start}>Edit</button> : null}>
            {editing ? (
                <div className="sv-edit">
                    <textarea className="sx-input" rows={8} maxLength={INSTRUCTIONS_LIMIT} autoFocus value={draft} aria-label="Space instructions"
                        placeholder="e.g. You are a market access analyst. Answer concisely, use tables for comparisons and cite regulators first."
                        onChange={event => setDraft(event.target.value)} />
                    <div className="sv-edit-foot">
                        <span className={`sv-counter ${draft.length > INSTRUCTIONS_LIMIT * 0.9 ? "sv-counter--warn" : ""}`}>{draft.length.toLocaleString()} / {INSTRUCTIONS_LIMIT.toLocaleString()}</span>
                        <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => { setEditing(false); setError(""); }} disabled={saving}>Cancel</button>
                        <button className="sx-btn sx-btn--primary sx-btn--sm" onClick={() => void submit()} disabled={saving}>
                            {saving && <Loader2 size={12} className="sx-spin" />} Save
                        </button>
                    </div>
                </div>
            ) : space.instructions ? (
                <>
                    <p className={`sv-instructions ${long && !expanded ? "sv-instructions--clamped" : ""}`}>{space.instructions}</p>
                    {long && <button className="sv-rail-action sv-rail-more" onClick={() => setExpanded(!expanded)}>{expanded ? "Show less" : "Show more"}</button>}
                </>
            ) : editable ? (
                <button className="sv-add-row" onClick={start}><Plus size={14} /> Tell Corten how to answer here</button>
            ) : <p className="sv-quiet">No instructions.</p>}
            {error && <p className="sx-error" role="alert">{error}</p>}
        </RailSection>
    );
}

function fileProblem(file: File): string | null {
    const extension = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    if (!file.name.includes(".") || !EXTENSIONS.has(extension)) return "Unsupported type. Use PDF, Office, HTML or text files.";
    if (file.size > MAX_FILE_BYTES) return "Larger than 25 MB.";
    if (file.size === 0) return "This file is empty.";
    return null;
}

function fileKind(name: string): string {
    const extension = (name.split(".").pop() ?? "").toUpperCase();
    return extension.length <= 5 ? extension : "File";
}

function FilesSection({ space, files, editable, onFiles, onCount }: {
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
        <RailSection id="files-heading" title="Files" count={files.length} className={dragging ? "sv-rail-section--drop" : ""}
            action={editable ? <button className="sv-rail-icon" aria-label="Upload files" title="Upload files" onClick={() => inputRef.current?.click()}><Plus size={16} /></button> : null}
            onDragOver={event => { if (editable && event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
            onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
            onDrop={event => { if (!editable) return; event.preventDefault(); setDragging(false); add(event.dataTransfer.files); }}>
            {editable && <input ref={inputRef} type="file" multiple accept={ACCEPTED_FILES} hidden
                onChange={event => { if (event.target.files?.length) add(event.target.files); event.target.value = ""; }} />}
            {dragging && <div className="sv-drop-hint"><Upload size={16} aria-hidden="true" /> Drop to add to this Space</div>}
            {uploads.length > 0 && (
                <ul className="sv-files" aria-label="Uploads">
                    {uploads.map(item => (
                        <li key={item.key} className={`sv-file ${item.status === "failed" ? "sv-file--failed" : ""}`}>
                            <span className="sv-file-badge" aria-hidden="true">{fileKind(item.name)}</span>
                            <div className="sv-file-text">
                                <span className="sv-file-name">{item.name}</span>
                                {item.status === "failed" ? <span className="sv-file-error" role="alert">{item.error}</span> : (
                                    <span className="sv-progress" role="progressbar" aria-label={`Uploading ${item.name}`} aria-valuemin={0} aria-valuemax={100}
                                        aria-valuenow={Math.round(item.progress * 100)}>
                                        <span style={{ width: `${Math.max(4, item.progress * 100)}%` }} />
                                    </span>
                                )}
                                {item.status === "uploading" && item.progress >= 1 && <span className="sv-file-meta">Reading and indexing…</span>}
                                {item.status === "queued" && <span className="sv-file-meta">Waiting</span>}
                            </div>
                            {item.status === "failed" && (
                                <span className="sv-file-actions sv-file-actions--shown">
                                    {item.retryable && !fileProblem(item.file) && <button className="sv-rail-action" onClick={() => retry(item)}>Retry</button>}
                                    <button className="sx-icon-btn" aria-label={`Dismiss ${item.name}`} onClick={() => setUploads(current => current.filter(entry => entry.key !== item.key))}><X size={13} /></button>
                                </span>
                            )}
                        </li>
                    ))}
                </ul>
            )}
            {error && <p className="sx-error" role="alert">{error}</p>}
            {files.length > 0 ? (
                <ul className="sv-files">
                    {files.map(file => (
                        <li key={file.id} className="sv-file">
                            <span className="sv-file-badge" aria-hidden="true">{fileKind(file.name)}</span>
                            <div className="sv-file-text">
                                <a className="sv-file-name" href={spacesApi.downloadUrl(space.id, file.id)} title={`Download ${file.name}`}>{file.name}</a>
                                <span className="sv-file-meta">{formatBytes(file.size)} · {relativeTime(file.createdAt)}{space.memberCount > 1 && file.uploadedBy ? ` · ${file.uploadedBy}` : ""}</span>
                            </div>
                            {confirming === file.id ? (
                                <span className="sv-inline-confirm">
                                    <button className="sx-btn sx-btn--danger sx-btn--sm" onClick={() => void remove(file)}>Remove</button>
                                    <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => setConfirming("")}>Cancel</button>
                                </span>
                            ) : (
                                <span className="sv-file-actions">
                                    <a className="sx-icon-btn" href={spacesApi.downloadUrl(space.id, file.id)} aria-label={`Download ${file.name}`}><Download size={14} /></a>
                                    {editable && <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Remove ${file.name}`} onClick={() => setConfirming(file.id)}><Trash2 size={14} /></button>}
                                </span>
                            )}
                        </li>
                    ))}
                </ul>
            ) : uploads.length === 0 && (editable ? (
                <button className="sv-add-row sv-add-row--drop" onClick={() => inputRef.current?.click()}>
                    <Upload size={14} /> <span>Add PDFs, Office files or notes<small>Answers search and cite them · up to 25 MB each</small></span>
                </button>
            ) : <p className="sv-quiet">No files.</p>)}
        </RailSection>
    );
}

function LinksSection({ space, editable, onSave }: { space: Space; editable: boolean; onSave: (fields: SpaceFields) => Promise<void> }) {
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
        <RailSection id="links-heading" title="Links" count={space.links.length}
            action={editable && !adding ? <button className="sv-rail-icon" aria-label="Add a link" title="Add a link" onClick={() => setAdding(true)}><Plus size={16} /></button> : null}>
            {space.links.length > 0 && (
                <ul className="sv-links">
                    {space.links.map(link => (
                        <li key={link} className="sv-link">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(linkHost(link))}&sz=32`} alt="" width={16} height={16}
                                onError={event => { (event.target as HTMLImageElement).style.visibility = "hidden"; }} />
                            <a href={link} target="_blank" rel="noopener noreferrer" title={link}>{linkHost(link)}<ExternalLink size={11} aria-hidden="true" /></a>
                            {editable && <button className="sx-icon-btn" aria-label={`Remove ${linkHost(link)}`} disabled={saving}
                                onClick={() => void update(space.links.filter(item => item !== link))}><X size={13} /></button>}
                        </li>
                    ))}
                </ul>
            )}
            {adding && (
                <form className="sv-link-form" onSubmit={add}>
                    <input className="sx-input" autoFocus placeholder="example.com/reports" value={value} aria-label="Link to add" maxLength={2048}
                        onChange={event => { setValue(event.target.value); setError(""); }}
                        onKeyDown={event => { if (event.key === "Escape") { setAdding(false); setError(""); } }} />
                    <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={!value.trim() || saving}>
                        {saving ? <Loader2 size={12} className="sx-spin" /> : "Add"}
                    </button>
                </form>
            )}
            {!space.links.length && !adding && (editable
                ? <button className="sv-add-row" onClick={() => setAdding(true)}><Plus size={14} /> Add sites to search first</button>
                : <p className="sv-quiet">No links.</p>)}
            {error && <p className="sx-error" role="alert">{error}</p>}
        </RailSection>
    );
}

function SearchSection({ space, editable, hasFiles, onSave }: { space: Space; editable: boolean; hasFiles: boolean; onSave: (fields: SpaceFields) => Promise<void> }) {
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
        <RailSection id="search-heading" title="Sources">
            <div className="sv-switch-row">
                <span>
                    <span className="sv-switch-label" id="web-search-label">Search the web</span>
                    <span className="sv-switch-hint">{space.webSearch ? "Web results alongside this Space's files" : "Only this Space's files are used"}</span>
                </span>
                <button role="switch" aria-checked={space.webSearch} aria-labelledby="web-search-label" className="sx-switch"
                    disabled={!editable || saving} onClick={() => void toggle()}><span /></button>
            </div>
            {!space.webSearch && !hasFiles && <p className="sx-warning"><AlertCircle size={13} aria-hidden="true" /> Add files so answers have something to draw on.</p>}
            {error && <p className="sx-error" role="alert">{error}</p>}
        </RailSection>
    );
}
