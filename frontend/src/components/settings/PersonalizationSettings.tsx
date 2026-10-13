"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Download, FileText, Image as ImageIcon, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { personalizationApi, STYLES, type Memory, type Preferences, type StoredFile } from "@/lib/chatApi";
import { formatBytes, relativeTime } from "@/lib/spacesApi";

/** Preferences, response style, memory and stored files, all user-visible and user-controlled. */
export default function PersonalizationSettings({ section = "responses" }: { section?: "responses" | "memory" | "files" }) {
    const [prefs, setPrefs] = useState<Preferences | null>(null);
    const [draft, setDraft] = useState({ personal_instructions: "", custom_style: "" });
    const [memories, setMemories] = useState<Memory[] | null>(null);
    const [files, setFiles] = useState<StoredFile[] | null>(null);
    const [status, setStatus] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState("");
    const [newMemory, setNewMemory] = useState("");
    const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
    const [confirmClear, setConfirmClear] = useState(false);
    const [confirmFile, setConfirmFile] = useState<string | null>(null);
    const [styleChoice, setStyleChoice] = useState<Preferences["style"] | null>(null);
    const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
    const [loading, setLoading] = useState(true);
    const generation = useRef(0);
    const initialized = useRef(false);
    const operation = useRef(false);
    const load = useCallback(async () => {
        const current = ++generation.current;
        const results = await Promise.allSettled([personalizationApi.get(), personalizationApi.memories(), personalizationApi.files()]);
        if (current !== generation.current) return;
        const failures: Record<string, string> = {};
        results.forEach((result, index) => {
            if (result.status === "rejected") failures[["prefs", "memories", "files"][index]] = result.reason instanceof Error ? result.reason.message : "Unable to load. Please retry.";
        });
        if (results[0].status === "fulfilled") {
            const p = results[0].value; setPrefs(p);
            if (!initialized.current) { setDraft({ personal_instructions: p.personal_instructions, custom_style: p.custom_style }); initialized.current = true; }
        }
        if (results[1].status === "fulfilled") setMemories(results[1].value);
        if (results[2].status === "fulfilled") setFiles(results[2].value);
        setLoadErrors(failures); setLoading(false);
    }, []);

    useEffect(() => {
        let cancelled = false;
        void Promise.resolve().then(() => { if (!cancelled) void load(); });
        const requests = generation;
        return () => { cancelled = true; requests.current++; };
    }, [load]);

    const run = async (key: string, action: () => Promise<void>, done = "") => {
        if (operation.current) return;
        operation.current = true;
        setBusy(key); setError(""); setStatus("");
        try { await action(); if (done) setStatus(done); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "The change could not be saved."); }
        finally { operation.current = false; setBusy(""); }
    };
    const update = (changes: Partial<Preferences>, done: string) => run("prefs", async () => {
        setPrefs(await personalizationApi.update(changes));
        if (changes.style) setStyleChoice(null);
    }, done);

    const title = section === "responses" ? "Responses" : section === "memory" ? "Memory" : "Files";
    const panel = (children: ReactNode, pending = false) => <><section className="account-panel cx-settings" id={`settings-panel-${section}`} role="tabpanel" aria-labelledby={`settings-tab-${section}`} tabIndex={0} aria-busy={pending}>{children}</section>{(["responses", "memory", "files"] as const).filter(id => id !== section).map(id => <section key={id} id={`settings-panel-${id}`} role="tabpanel" aria-labelledby={`settings-tab-${id}`} hidden />)}</>;
    const unavailable = section === "files" ? files === null : prefs === null || (section === "memory" && memories === null);
    const loadError = section === "files" ? loadErrors.files : loadErrors.prefs || (section === "memory" ? loadErrors.memories : "");
    if (unavailable) return panel(<><h2>{title}</h2>{loading ? <div className="sx-skeleton sx-skeleton--panel" /> : <><p role="alert" className="sx-error">{loadError || "Unable to load. Please retry."}</p><button className="settings-button" disabled={!!busy} onClick={() => { setLoading(true); void load(); }}>Retry</button></>}</>, loading);
    const selectedStyle = styleChoice ?? prefs?.style;

    return panel(
        <>
            <h2>{title}</h2>
            {(status || error) && <p role={error ? "alert" : "status"} className={error ? "sx-error" : "cx-settings-status"}>{error || status}</p>}

            {prefs && <div className="cx-settings-block" hidden={section !== "responses"}>
                <h3>Custom instructions</h3>
                <p className="cx-settings-help">Role, units and preferred format.</p>
                <textarea className="sx-input" rows={4} maxLength={2000} value={draft.personal_instructions} aria-label="Personal preferences"
                    placeholder="Add your response preferences"
                    onChange={event => setDraft({ ...draft, personal_instructions: event.target.value })} />
                <div className="cx-settings-row">
                    <span className="sx-counter">{draft.personal_instructions.length} / 2,000</span>
                    <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={!!busy || draft.personal_instructions.trim() === prefs.personal_instructions}
                        onClick={() => void update({ personal_instructions: draft.personal_instructions }, "Preferences saved.")}>Save</button>
                </div>
            </div>}

            {prefs && <div className="cx-settings-block" hidden={section !== "responses"}>
                <h3>Response style</h3>
                <div className="cx-style-grid" role="radiogroup" aria-label="Response style" aria-busy={!!busy} onKeyDown={event => {
                    if (busy || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
                    event.preventDefault();
                    const index = STYLES.findIndex(style => style.value === selectedStyle);
                    const next = event.key === "Home" ? 0 : event.key === "End" ? STYLES.length - 1 : (index + (["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 1) + STYLES.length) % STYLES.length;
                    const button = document.getElementById(`settings-style-${STYLES[next].value}`);
                    button?.focus(); button?.click();
                }}>
                    {STYLES.map(style => (
                        <button key={style.value} id={`settings-style-${style.value}`} type="button" role="radio" aria-checked={selectedStyle === style.value} tabIndex={selectedStyle === style.value ? 0 : -1}
                            className={`cx-style ${selectedStyle === style.value ? "cx-style--active" : ""}`} aria-disabled={!!busy}
                            onClick={() => { if (busy) return; if (style.value === "custom") setStyleChoice("custom"); else if (style.value !== prefs.style) void update({ style: style.value }, `${style.label} style selected.`); else setStyleChoice(null); }}>
                            <strong>{style.label}</strong><span>{style.description}</span>
                        </button>
                    ))}
                </div>
                {selectedStyle === "custom" && (
                    <div className="cx-settings-custom">
                        <textarea className="sx-input" rows={3} maxLength={1000} value={draft.custom_style} aria-label="Custom style"
                            placeholder="Describe your preferred response style"
                            onChange={event => setDraft({ ...draft, custom_style: event.target.value })} />
                        <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={!!busy || !draft.custom_style.trim() || (prefs.style === "custom" && draft.custom_style.trim() === prefs.custom_style)}
                            onClick={() => void update({ style: "custom", custom_style: draft.custom_style }, "Custom style saved.")}>Use this style</button>
                    </div>
                )}
            </div>}

            {prefs && memories && <div className="cx-settings-block" hidden={section !== "memory"}>
                <div className="cx-settings-row">
                    <div>
                        <h3>Save memories across chats</h3>
                        <p className="cx-settings-help">Private chats are excluded.</p>
                    </div>
                    <button role="switch" aria-checked={prefs.memory_enabled} aria-label="Remember facts from chats" className="sx-switch" disabled={!!busy}
                        onClick={() => void update({ memory_enabled: !prefs.memory_enabled }, prefs.memory_enabled ? "Memory turned off." : "Memory turned on.")}><span /></button>
                </div>
                <form className="cx-memory-add" onSubmit={event => { event.preventDefault(); const text = newMemory.trim(); if (!text) return;
                    void run("add", async () => { const added = await personalizationApi.addMemory(text); if ("id" in added) setMemories([added, ...memories]); setNewMemory(current => current.trim() === text ? "" : current); },
                        "Memory added."); }}>
                    <input className="sx-input" value={newMemory} maxLength={500} placeholder="Add something Corten should remember…" aria-label="New memory"
                        onChange={event => setNewMemory(event.target.value)} />
                    <button className="sx-btn sx-btn--secondary sx-btn--sm" disabled={!newMemory.trim() || !!busy}><Plus size={13} /> Add</button>
                </form>
                {memories.length === 0 ? <p className="sx-placeholder">Nothing remembered yet.</p> : (
                    <ul className="cx-memory-list">
                        {memories.map(memory => (
                            <li key={memory.id} className="cx-memory">
                                {editing?.id === memory.id ? (
                                    <form className="cx-memory-edit" onSubmit={event => { event.preventDefault();
                                        void run(memory.id, async () => { const saved = await personalizationApi.editMemory(memory.id, editing.text);
                                            setMemories(memories.map(item => item.id === memory.id ? saved : item)); setEditing(null); }, "Memory updated."); }}>
                                        <input className="sx-input" autoFocus value={editing.text} maxLength={500} aria-label="Edit memory" disabled={!!busy}
                                            onChange={event => setEditing({ id: memory.id, text: event.target.value })} />
                                        <button className="sx-icon-btn" aria-label="Save memory" disabled={!editing.text.trim() || !!busy}><Check size={14} /></button>
                                        <button type="button" className="sx-icon-btn" aria-label="Cancel" disabled={!!busy} onClick={() => setEditing(null)}><X size={14} /></button>
                                    </form>
                                ) : (
                                    <>
                                        <span className="cx-memory-text">{memory.content}</span>
                                        <span className="cx-memory-meta">{memory.source === "auto" ? "Learned" : "Added"} {relativeTime(memory.updatedAt).toLowerCase()}</span>
                                        <button className="sx-icon-btn" aria-label={`Edit memory: ${memory.content}`} disabled={!!busy} onClick={() => setEditing({ id: memory.id, text: memory.content })}><Pencil size={13} /></button>
                                        <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Forget: ${memory.content}`} disabled={!!busy}
                                            onClick={() => void run(memory.id, async () => { await personalizationApi.deleteMemory(memory.id); setMemories(memories.filter(item => item.id !== memory.id)); }, "Memory deleted.")}><Trash2 size={13} /></button>
                                    </>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
                {memories.length > 0 && (confirmClear ? (
                    <div className="sx-inline-confirm cx-memory-clear">
                        <span>Delete all {memories.length} memories?</span>
                        <button className="sx-btn sx-btn--danger sx-btn--sm" disabled={!!busy} onClick={() => void run("clear", async () => { await personalizationApi.clearMemories(); setMemories([]); setConfirmClear(false); }, "All memories deleted.")}>Delete all</button>
                        <button className="sx-btn sx-btn--ghost sx-btn--sm" disabled={!!busy} onClick={() => setConfirmClear(false)}>Cancel</button>
                    </div>
                ) : <button className="sx-btn sx-btn--danger-ghost sx-btn--sm cx-memory-clear" disabled={!!busy} onClick={() => setConfirmClear(true)}>Delete all memories</button>)}
            </div>}

            {files && <div className="cx-settings-block" hidden={section !== "files"}>
                <p className="cx-settings-help">Chat attachments and generated files · Retained for 90 days</p>
                {files.length === 0 ? <p className="sx-placeholder">No files yet.</p> : (
                    <ul className="sx-file-list">
                        {files.map(file => (
                            <li key={file.id} className="sx-file">
                                {file.kind === "image" ? <ImageIcon size={16} className="sx-file-icon" aria-hidden="true" /> : <FileText size={16} className="sx-file-icon" aria-hidden="true" />}
                                <div className="sx-file-text">
                                    <a className="sx-file-name" href={file.url} download={file.name}>{file.name}</a>
                                    <span className="sx-muted">{file.kind === "generated" ? "Created by Corten" : file.kind === "image" ? "Image" : "Document"} · {formatBytes(file.size)} · {relativeTime(file.createdAt)}</span>
                                </div>
                                <span className="sx-row">
                                    <a className="sx-icon-btn" href={file.url} download={file.name} aria-label={`Download ${file.name}`}><Download size={13} /></a>
                                    <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Delete ${file.name}`} disabled={!!busy}
                                        onClick={() => setConfirmFile(file.id)}>
                                        {busy === file.id ? <Loader2 size={13} className="sx-spin" /> : <Trash2 size={13} />}
                                    </button>
                                </span>
                                {confirmFile === file.id && <div className="sx-inline-confirm settings-file-confirm"><span>Delete this file?</span><button className="sx-btn sx-btn--danger sx-btn--sm" disabled={!!busy} onClick={() => void run(file.id, async () => { await personalizationApi.deleteFile(file.id); setFiles(files.filter(item => item.id !== file.id)); setConfirmFile(null); }, "File deleted.")}>Delete file</button><button className="sx-btn sx-btn--ghost sx-btn--sm" disabled={!!busy} onClick={() => setConfirmFile(null)}>Cancel</button></div>}
                            </li>
                        ))}
                    </ul>
                )}
            </div>}
        </>
    );
}
