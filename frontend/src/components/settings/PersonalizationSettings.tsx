"use client";
import { useEffect, useState } from "react";
import { Brain, Check, Download, FileText, Image as ImageIcon, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";
import { personalizationApi, STYLES, type Memory, type Preferences, type StoredFile } from "@/lib/chatApi";
import { formatBytes, relativeTime } from "@/lib/spacesApi";

/** Preferences, response style, memory and stored files, all user-visible and user-controlled. */
export default function PersonalizationSettings() {
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

    useEffect(() => {
        Promise.all([personalizationApi.get(), personalizationApi.memories(), personalizationApi.files()]).then(([p, m, f]) => {
            setPrefs(p);
            setDraft({ personal_instructions: p.personal_instructions, custom_style: p.custom_style });
            setMemories(m);
            setFiles(f);
        }, failure => setError(failure instanceof Error ? failure.message : "Personalization could not be loaded."));
    }, []);

    const run = async (key: string, action: () => Promise<void>, done = "") => {
        setBusy(key); setError(""); setStatus("");
        try { await action(); if (done) setStatus(done); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "The change could not be saved."); }
        finally { setBusy(""); }
    };
    const update = (changes: Partial<Preferences>, done: string) => run("prefs", async () => setPrefs(await personalizationApi.update(changes)), done);

    if (error && !prefs) return <section className="account-panel" id="personalization"><p role="alert" className="sx-error">{error}</p></section>;
    if (!prefs || !memories || !files) return <section className="account-panel" id="personalization" aria-busy="true"><div className="sx-skeleton sx-skeleton--panel" /></section>;

    return (
        <section className="account-panel cx-settings" id="personalization" aria-labelledby="personalization-heading">
            <h2 id="personalization-heading">Personalization</h2>
            {(status || error) && <p role={error ? "alert" : "status"} className={error ? "sx-error" : "cx-settings-status"}>{error || status}</p>}

            <div className="cx-settings-block">
                <h3>About you and your preferences</h3>
                <p className="cx-settings-help">Corten considers this in every answer, for example your role, industry, units, or preferred format.</p>
                <textarea className="sx-input" rows={4} maxLength={2000} value={draft.personal_instructions} aria-label="Personal preferences"
                    placeholder="e.g. I'm a market access lead in Germany. Use metric units and euros, and lead with a short summary."
                    onChange={event => setDraft({ ...draft, personal_instructions: event.target.value })} />
                <div className="cx-settings-row">
                    <span className="sx-counter">{draft.personal_instructions.length} / 2,000</span>
                    <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={busy === "prefs" || draft.personal_instructions.trim() === prefs.personal_instructions}
                        onClick={() => void update({ personal_instructions: draft.personal_instructions }, "Preferences saved.")}>Save</button>
                </div>
            </div>

            <div className="cx-settings-block">
                <h3>Response style</h3>
                <div className="cx-style-grid" role="radiogroup" aria-label="Response style">
                    {STYLES.map(style => (
                        <button key={style.value} type="button" role="radio" aria-checked={prefs.style === style.value}
                            className={`cx-style ${prefs.style === style.value ? "cx-style--active" : ""}`} disabled={busy === "prefs"}
                            onClick={() => style.value !== "custom" && style.value !== prefs.style ? void update({ style: style.value }, `${style.label} style selected.`)
                                : setPrefs({ ...prefs, style: style.value })}>
                            <strong>{style.label}</strong><span>{style.description}</span>
                        </button>
                    ))}
                </div>
                {prefs.style === "custom" && (
                    <div className="cx-settings-custom">
                        <textarea className="sx-input" rows={3} maxLength={1000} value={draft.custom_style} aria-label="Custom style"
                            placeholder="e.g. Write like a McKinsey partner: executive summary first, numbered recommendations, no jargon."
                            onChange={event => setDraft({ ...draft, custom_style: event.target.value })} />
                        <button className="sx-btn sx-btn--primary sx-btn--sm" disabled={busy === "prefs" || !draft.custom_style.trim()}
                            onClick={() => void update({ style: "custom", custom_style: draft.custom_style }, "Custom style saved.")}>Use this style</button>
                    </div>
                )}
            </div>

            <div className="cx-settings-block">
                <div className="cx-settings-row">
                    <div>
                        <h3><Brain size={15} aria-hidden="true" /> Memory</h3>
                        <p className="cx-settings-help">Corten remembers useful facts you share, such as your role or preferences, across chats. Private chats are never remembered, and you control everything here.</p>
                    </div>
                    <button role="switch" aria-checked={prefs.memory_enabled} aria-label="Remember facts from chats" className="sx-switch" disabled={busy === "prefs"}
                        onClick={() => void update({ memory_enabled: !prefs.memory_enabled }, prefs.memory_enabled ? "Memory turned off." : "Memory turned on.")}><span /></button>
                </div>
                <form className="cx-memory-add" onSubmit={event => { event.preventDefault(); const text = newMemory.trim(); if (!text) return;
                    void run("add", async () => { const added = await personalizationApi.addMemory(text); if ("id" in added) setMemories([added, ...memories]); setNewMemory(""); },
                        "Memory added."); }}>
                    <input className="sx-input" value={newMemory} maxLength={500} placeholder="Add something Corten should remember…" aria-label="New memory"
                        onChange={event => setNewMemory(event.target.value)} />
                    <button className="sx-btn sx-btn--secondary sx-btn--sm" disabled={!newMemory.trim() || busy === "add"}><Plus size={13} /> Add</button>
                </form>
                {memories.length === 0 ? <p className="sx-placeholder">Nothing remembered yet.</p> : (
                    <ul className="cx-memory-list">
                        {memories.map(memory => (
                            <li key={memory.id} className="cx-memory">
                                {editing?.id === memory.id ? (
                                    <form className="cx-memory-edit" onSubmit={event => { event.preventDefault();
                                        void run(memory.id, async () => { const saved = await personalizationApi.editMemory(memory.id, editing.text);
                                            setMemories(memories.map(item => item.id === memory.id ? saved : item)); setEditing(null); }, "Memory updated."); }}>
                                        <input className="sx-input" autoFocus value={editing.text} maxLength={500} aria-label="Edit memory"
                                            onChange={event => setEditing({ id: memory.id, text: event.target.value })} />
                                        <button className="sx-icon-btn" aria-label="Save memory" disabled={!editing.text.trim()}><Check size={14} /></button>
                                        <button type="button" className="sx-icon-btn" aria-label="Cancel" onClick={() => setEditing(null)}><X size={14} /></button>
                                    </form>
                                ) : (
                                    <>
                                        <span className="cx-memory-text">{memory.content}</span>
                                        <span className="cx-memory-meta">{memory.source === "auto" ? "Learned" : "Added"} {relativeTime(memory.updatedAt).toLowerCase()}</span>
                                        <button className="sx-icon-btn" aria-label={`Edit memory: ${memory.content}`} onClick={() => setEditing({ id: memory.id, text: memory.content })}><Pencil size={13} /></button>
                                        <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Forget: ${memory.content}`} disabled={busy === memory.id}
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
                        <button className="sx-btn sx-btn--danger sx-btn--sm" onClick={() => void run("clear", async () => { await personalizationApi.clearMemories(); setMemories([]); setConfirmClear(false); }, "All memories deleted.")}>Delete all</button>
                        <button className="sx-btn sx-btn--ghost sx-btn--sm" onClick={() => setConfirmClear(false)}>Cancel</button>
                    </div>
                ) : <button className="sx-btn sx-btn--danger-ghost sx-btn--sm cx-memory-clear" onClick={() => setConfirmClear(true)}>Delete all memories</button>)}
            </div>

            <div className="cx-settings-block">
                <h3>Your files</h3>
                <p className="cx-settings-help">Files you attached and files Corten created. They are private to you and deleted automatically after 90 days.</p>
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
                                    <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Delete ${file.name}`} disabled={busy === file.id}
                                        onClick={() => void run(file.id, async () => { await personalizationApi.deleteFile(file.id); setFiles(files.filter(item => item.id !== file.id)); }, "File deleted.")}>
                                        {busy === file.id ? <Loader2 size={13} className="sx-spin" /> : <Trash2 size={13} />}
                                    </button>
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </section>
    );
}
