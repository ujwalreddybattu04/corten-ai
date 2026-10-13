"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Paperclip, X, FileText, ChevronDown, Check, Zap, Sparkles, Brain, Wand2, Loader2, AlertCircle, SlidersHorizontal } from "lucide-react";
import { ANSWER_MODES, ATTACHMENT_ACCEPT, getAnswerMode, setAnswerMode, type AnswerMode } from "@/lib/chatApi";
import { formatBytes } from "@/lib/spacesApi";
import type { PendingAttachment } from "@/hooks/useAttachments";

const MODE_ICONS = { auto: Wand2, fast: Zap, pro: Sparkles, think: Brain };

/** The answer mode chooser shared by the home search bar and follow-up composer. */
export function ModeMenu({ compact = false }: { compact?: boolean }) {
    const [mode, setMode] = useState<AnswerMode>("auto");
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
        const sync = () => setMode(getAnswerMode());
        sync();
        window.addEventListener("corten_answer_mode", sync);
        return () => window.removeEventListener("corten_answer_mode", sync);
    }, []);
    useEffect(() => {
        if (!open) return;
        const close = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
        const key = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
        document.addEventListener("mousedown", close);
        document.addEventListener("keydown", key);
        return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", key); };
    }, [open]);
    const current = ANSWER_MODES.find(item => item.value === mode) ?? ANSWER_MODES[0];
    const Icon = MODE_ICONS[current.value];
    return (
        <div className="cx-mode" ref={ref}>
            <button type="button" className={`cx-mode-btn ${mode !== "auto" ? "cx-mode-btn--active" : ""}`} aria-haspopup="menu" aria-expanded={open}
                aria-label={`Answer mode: ${current.label}`} onClick={() => setOpen(!open)}>
                <Icon size={13} aria-hidden="true" />{!compact && <span>{current.label}</span>}<ChevronDown size={12} aria-hidden="true" />
            </button>
            {open && (
                <div className="cx-mode-menu" role="menu" aria-label="Answer mode">
                    {ANSWER_MODES.map(item => {
                        const ItemIcon = MODE_ICONS[item.value];
                        return (
                            <button key={item.value} type="button" role="menuitemradio" aria-checked={item.value === mode} className="cx-mode-item"
                                onClick={() => { setAnswerMode(item.value); setOpen(false); }}>
                                <ItemIcon size={15} aria-hidden="true" />
                                <span className="cx-mode-text"><strong>{item.label}</strong><span>{item.description}</span></span>
                                {item.value === mode && <Check size={14} aria-hidden="true" />}
                            </button>
                        );
                    })}
                    <Link href="/settings#personalization" className="cx-mode-footer" onClick={() => setOpen(false)}>
                        <SlidersHorizontal size={13} aria-hidden="true" /> Style, memory and personalization
                    </Link>
                </div>
            )}
        </div>
    );
}

/** Paperclip button that opens the system file picker. */
export function AttachButton({ onFiles, disabled }: { onFiles: (files: FileList) => void; disabled?: boolean }) {
    const input = useRef<HTMLInputElement>(null);
    return (
        <>
            <input ref={input} type="file" multiple hidden accept={ATTACHMENT_ACCEPT}
                onChange={event => { if (event.target.files?.length) onFiles(event.target.files); event.target.value = ""; }} />
            <button type="button" className="cx-attach-btn" aria-label="Attach files or images" title="Attach files or images (or paste and drop them)"
                disabled={disabled} onClick={() => input.current?.click()}>
                <Paperclip size={15} aria-hidden="true" />
            </button>
        </>
    );
}

/** Chips for files attached to the message being written. */
export function AttachmentTray({ items, onRemove }: { items: PendingAttachment[]; onRemove: (key: string) => void }) {
    if (!items.length) return null;
    return (
        <ul className="cx-tray" aria-label="Attachments">
            {items.map(item => (
                <li key={item.key} className={`cx-chip cx-chip--${item.status}`} title={item.error ?? item.name}>
                    {item.preview ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={item.preview} alt="" className="cx-chip-thumb" />
                    ) : (
                        <span className="cx-chip-icon" aria-hidden="true">{item.status === "failed" ? <AlertCircle size={15} /> : <FileText size={15} />}</span>
                    )}
                    <span className="cx-chip-text">
                        <span className="cx-chip-name">{item.name}</span>
                        <span className="cx-chip-meta">
                            {item.status === "failed" ? <span role="alert">{item.error}</span>
                                : item.status === "uploading" ? <>{item.progress < 1 ? `Uploading ${Math.round(item.progress * 100)}%` : "Reading…"}</>
                                : formatBytes(item.size)}
                        </span>
                    </span>
                    {item.status === "uploading" && <Loader2 size={13} className="sx-spin cx-chip-spin" aria-hidden="true" />}
                    <button type="button" className="cx-chip-remove" aria-label={`Remove ${item.name}`} onClick={() => onRemove(item.key)}><X size={12} /></button>
                    {item.status === "uploading" && <span className="cx-chip-progress" style={{ width: `${Math.max(6, item.progress * 100)}%` }} aria-hidden="true" />}
                </li>
            ))}
        </ul>
    );
}

/** Pasted or dropped files from a clipboard or drag event. */
export function filesFromTransfer(data: DataTransfer | null): File[] {
    if (!data) return [];
    return [...data.files].filter(file => file.size > 0);
}
