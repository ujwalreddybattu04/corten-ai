"use client";
import { useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { Paperclip, X, FileText, ChevronDown, Check, Zap, Sparkles, Brain, Wand2, Loader2, AlertCircle, SlidersHorizontal, ArrowUpRight } from "lucide-react";
import { ANSWER_MODES, ATTACHMENT_ACCEPT, getAnswerMode, setAnswerMode, type AnswerMode } from "@/lib/chatApi";
import { formatBytes } from "@/lib/spacesApi";
import type { PendingAttachment } from "@/hooks/useAttachments";

const MODE_ICONS = { auto: Wand2, fast: Zap, pro: Sparkles, think: Brain };
const subscribeMode = (callback: () => void) => {
    window.addEventListener("corten_answer_mode", callback);
    return () => window.removeEventListener("corten_answer_mode", callback);
};
type MenuPosition = { top: number; left: number; maxHeight: number; maxWidth: number };

/** The answer mode chooser shared by the home search bar and follow-up composer. */
export function ModeMenu({ compact = false }: { compact?: boolean }) {
    const mode = useSyncExternalStore(subscribeMode, getAnswerMode, (): AnswerMode => "auto");
    const [open, setOpen] = useState(false);
    const [position, setPosition] = useState<MenuPosition | null>(null);
    const menuId = useId();
    const ref = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const menu = useRef<HTMLDivElement>(null);
    const focusPlaced = useRef(false);
    const closeAndFocus = () => { setOpen(false); trigger.current?.focus({ preventScroll: true }); };
    useLayoutEffect(() => {
        if (!open) return;
        let frame = 0;
        const place = () => {
            if (!trigger.current || !menu.current) return;
            const anchor = trigger.current.getBoundingClientRect();
            const viewport = window.visualViewport;
            const top = (viewport?.offsetTop ?? 0) + 12, left = (viewport?.offsetLeft ?? 0) + 12;
            const maxWidth = Math.max(1, (viewport?.width ?? window.innerWidth) - 24);
            const maxHeight = Math.max(1, (viewport?.height ?? window.innerHeight) - 24);
            const width = Math.min(menu.current.offsetWidth, maxWidth);
            const height = Math.min(menu.current.scrollHeight + menu.current.offsetHeight - menu.current.clientHeight, maxHeight);
            const bottom = top + maxHeight;
            const above = anchor.top - 8 - height;
            const below = anchor.bottom + 8;
            const preferBelow = !!ref.current?.closest(".search-bar");
            const y = preferBelow && below + height <= bottom ? below : above >= top ? above : below;
            const next = { top: Math.max(top, Math.min(y, bottom - height)), left: Math.max(left, Math.min(anchor.right - width, left + maxWidth - width)), maxHeight, maxWidth };
            setPosition(previous => previous && Object.keys(next).every(key => Math.abs(previous[key as keyof MenuPosition] - next[key as keyof MenuPosition]) < .5) ? previous : next);
        };
        const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(place); };
        place();
        const observer = new ResizeObserver(schedule);
        if (trigger.current) observer.observe(trigger.current);
        if (menu.current) observer.observe(menu.current);
        window.addEventListener("resize", schedule);
        document.addEventListener("scroll", schedule, true);
        window.visualViewport?.addEventListener("resize", schedule);
        window.visualViewport?.addEventListener("scroll", schedule);
        return () => { cancelAnimationFrame(frame); observer.disconnect(); window.removeEventListener("resize", schedule); document.removeEventListener("scroll", schedule, true); window.visualViewport?.removeEventListener("resize", schedule); window.visualViewport?.removeEventListener("scroll", schedule); };
    }, [open]);
    useLayoutEffect(() => {
        if (!open) { focusPlaced.current = false; return; }
        if (position && !focusPlaced.current) {
            menu.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus({ preventScroll: true });
            focusPlaced.current = true;
        }
    }, [open, position]);
    useEffect(() => {
        if (!open) return;
        const close = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node) && !menu.current?.contains(event.target as Node)) setOpen(false); };
        const key = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus({ preventScroll: true }); } };
        document.addEventListener("pointerdown", close);
        document.addEventListener("keydown", key);
        return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", key); };
    }, [open]);
    const current = ANSWER_MODES.find(item => item.value === mode) ?? ANSWER_MODES[0];
    const Icon = MODE_ICONS[current.value];
    return (
        <div className="cx-mode" ref={ref}>
            <button ref={trigger} type="button" className={`cx-mode-btn ${mode !== "auto" ? "cx-mode-btn--active" : ""}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
                aria-label={`Answer mode: ${current.label}`} onClick={() => setOpen(!open)} onKeyDown={event => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); } }}>
                <Icon size={14} aria-hidden="true" /><span>{compact && mode === "think" ? "Thinking" : current.label}</span><ChevronDown size={12} aria-hidden="true" />
            </button>
            {open && (
                createPortal(<div ref={menu} id={menuId} className="cx-mode-menu" role="menu" aria-label="Answer mode" style={{ ...position, visibility: position ? "visible" : "hidden" }} onKeyDown={event => {
                    if (event.key === "Tab") { closeAndFocus(); return; }
                    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
                    event.preventDefault();
                    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"], [role="menuitem"]') ?? []);
                    const index = items.indexOf(document.activeElement as HTMLElement);
                    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length;
                    items[next]?.focus();
                }}>
                    <div className="cx-mode-heading" role="presentation">Answer mode</div>
                    {ANSWER_MODES.map(item => {
                        const ItemIcon = MODE_ICONS[item.value];
                        return (
                            <button key={item.value} type="button" role="menuitemradio" tabIndex={-1} aria-checked={item.value === mode} className="cx-mode-item"
                                onClick={() => { setAnswerMode(item.value); closeAndFocus(); }}>
                                <span className="cx-mode-icon"><ItemIcon size={17} strokeWidth={1.7} aria-hidden="true" /></span>
                                <span className="cx-mode-text"><strong>{item.label}</strong><span>{item.description}</span></span>
                                <span className="cx-mode-check">{item.value === mode && <Check size={12} strokeWidth={2.2} aria-hidden="true" />}</span>
                            </button>
                        );
                    })}
                    <Link href="/settings#responses" scroll={false} role="menuitem" tabIndex={-1} className="cx-mode-footer" onClick={() => setOpen(false)}>
                        <SlidersHorizontal size={14} aria-hidden="true" />Response settings<ArrowUpRight size={14} aria-hidden="true" />
                    </Link>
                </div>, document.body)
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
