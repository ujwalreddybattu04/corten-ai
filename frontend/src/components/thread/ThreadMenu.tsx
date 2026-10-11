"use client";

import { useState, useRef, useEffect } from "react";
import {
    MoreHorizontal,
    Bookmark,
    FolderPlus,
    Pencil,
    FileText,
    FileCode2,
    FileDown,
    Trash2,
    Check,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

interface ThreadMenuProps {
    threadId: string | null;
    query: string;
    answer: string;
    history: Array<{ query: string; answer: string }>;
    onDelete?: () => void;
    onRename?: (newTitle: string) => void;
}

export default function ThreadMenu({
    threadId,
    query,
    answer,
    history,
    onDelete,
    onRename,
}: ThreadMenuProps) {
    const [open, setOpen] = useState(false);
    const [bookmarked, setBookmarked] = useState(false);
    const [bookmarkFeedback, setBookmarkFeedback] = useState(false);

    // Rename state
    const [showRename, setShowRename] = useState(false);
    const [renameValue, setRenameValue] = useState("");

    // Delete state
    const [showDeleteModal, setShowDeleteModal] = useState(false);

    // Space toast
    const [showSpaceToast, setShowSpaceToast] = useState(false);

    const menuRef = useRef<HTMLDivElement>(null);
    const renameInputRef = useRef<HTMLInputElement>(null);

    // Sync bookmark state from localStorage
    useEffect(() => {
        if (!threadId) return;
        try {
            const pins: string[] = JSON.parse(
                localStorage.getItem("corten_pinned_threads") || "[]"
            );
            setBookmarked(pins.includes(threadId));
        } catch {}
    }, [threadId, open]);

    // Close dropdown on outside click
    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [open]);

    // Focus rename input when modal opens
    useEffect(() => {
        if (showRename) {
            setTimeout(() => renameInputRef.current?.focus(), 50);
        }
    }, [showRename]);

    // ── BOOKMARK ──────────────────────────────────────────────────────────────
    const handleBookmark = () => {
        if (!threadId) return;
        try {
            const pins: string[] = JSON.parse(
                localStorage.getItem("corten_pinned_threads") || "[]"
            );
            const newPins = pins.includes(threadId)
                ? pins.filter((p) => p !== threadId)
                : [threadId, ...pins];
            localStorage.setItem("corten_pinned_threads", JSON.stringify(newPins));
            window.dispatchEvent(new Event("corten_threads_updated"));
            setBookmarked(!pins.includes(threadId));
            setBookmarkFeedback(true);
            setTimeout(() => setBookmarkFeedback(false), 1800);
        } catch {}
        setOpen(false);
    };

    // ── ADD TO SPACE ──────────────────────────────────────────────────────────
    const handleAddToSpace = () => {
        setOpen(false);
        setShowSpaceToast(true);
        setTimeout(() => setShowSpaceToast(false), 3000);
    };

    // ── RENAME ────────────────────────────────────────────────────────────────
    const handleRenameOpen = () => {
        if (!threadId) return;
        try {
            const threads = JSON.parse(
                localStorage.getItem("corten_threads") || "[]"
            );
            const thread = threads.find((t: any) => t.id === threadId);
            setRenameValue(thread?.title || query);
        } catch {
            setRenameValue(query);
        }
        setOpen(false);
        setShowRename(true);
    };

    const handleRenameSave = () => {
        const trimmed = renameValue.trim();
        if (!trimmed || !threadId) return;
        try {
            const threads = JSON.parse(
                localStorage.getItem("corten_threads") || "[]"
            );
            const updated = threads.map((t: any) =>
                t.id === threadId ? { ...t, title: trimmed } : t
            );
            localStorage.setItem("corten_threads", JSON.stringify(updated));
            window.dispatchEvent(new Event("corten_threads_updated"));
        } catch {}
        onRename?.(trimmed);
        setShowRename(false);
    };

    // ── EXPORT MARKDOWN ───────────────────────────────────────────────────────
    const handleExportMarkdown = () => {
        const sections = [
            ...history.map((h) => `## ${h.query}\n\n${h.answer}`),
            `## ${query}\n\n${answer}`,
        ].join("\n\n---\n\n");

        const filename =
            (query || "thread")
                .slice(0, 50)
                .replace(/[^\w\s-]/g, "")
                .trim()
                .replace(/\s+/g, "-") || "thread";

        const blob = new Blob([sections], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${filename}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        setOpen(false);
    };

    // ── EXPORT PDF ────────────────────────────────────────────────────────────
    const handleExportPDF = () => {
        setOpen(false);
        // Brief delay so the menu closes before print dialog opens
        setTimeout(() => window.print(), 120);
    };

    // ── EXPORT DOCX ──────────────────────────────────────────────────────────
    const handleExportDocx = () => {
        const escapeHtml = (s: string) =>
            s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        const mdToHtml = (md: string) =>
            md
                .replace(/^### (.+)$/gm, "<h3>$1</h3>")
                .replace(/^## (.+)$/gm, "<h2>$1</h2>")
                .replace(/^# (.+)$/gm, "<h1>$1</h1>")
                .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                .replace(/\*(.+?)\*/g, "<em>$1</em>")
                .replace(/`(.+?)`/g, "<code>$1</code>")
                .replace(/\n\n/g, "</p><p>")
                .replace(/\n/g, "<br>");

        const sections = [
            ...history.map(
                (h) =>
                    `<h2 style="color:#1a1a2e;font-size:15pt;margin-top:18pt;">${escapeHtml(h.query)}</h2><p>${mdToHtml(h.answer)}</p>`
            ),
            `<h2 style="color:#1a1a2e;font-size:15pt;margin-top:18pt;">${escapeHtml(query)}</h2><p>${mdToHtml(answer)}</p>`,
        ].join('<hr style="border:1px solid #e0e0e8;margin:18pt 0;">');

        const docHtml = `
<html xmlns:w="urn:schemas-microsoft-com:office:word">
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: Calibri, 'Segoe UI', sans-serif; font-size: 11pt; line-height: 1.6; margin: 2cm; color: #1a1a2e; }
    h1 { font-size: 18pt; } h2 { font-size: 15pt; } h3 { font-size: 13pt; }
    p { margin-bottom: 8pt; }
    code { font-family: 'Courier New', monospace; background: #f4f4f8; padding: 1pt 3pt; }
    strong { font-weight: 700; } em { font-style: italic; }
  </style>
</head>
<body>
  <h1 style="font-size:20pt;color:#1a1a2e;margin-bottom:4pt;">${escapeHtml(query)}</h1>
  <p style="color:#888;font-size:9pt;margin-bottom:24pt;">Exported from Orivanta AI · ${new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</p>
  ${sections}
</body>
</html>`;

        const filename =
            (query || "thread")
                .slice(0, 50)
                .replace(/[^\w\s-]/g, "")
                .trim()
                .replace(/\s+/g, "-") || "thread";

        const blob = new Blob([docHtml], { type: "application/msword" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${filename}.doc`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        setOpen(false);
    };

    // ── DELETE ────────────────────────────────────────────────────────────────
    const handleDeleteConfirm = () => {
        if (!threadId) return;
        try {
            const threads = JSON.parse(
                localStorage.getItem("corten_threads") || "[]"
            );
            localStorage.setItem(
                "corten_threads",
                JSON.stringify(threads.filter((t: any) => t.id !== threadId))
            );
            const pins: string[] = JSON.parse(
                localStorage.getItem("corten_pinned_threads") || "[]"
            );
            localStorage.setItem(
                "corten_pinned_threads",
                JSON.stringify(pins.filter((p) => p !== threadId))
            );
            window.dispatchEvent(new Event("corten_threads_updated"));
        } catch {}
        setShowDeleteModal(false);
        onDelete?.();
    };

    // ── Thread title display ──────────────────────────────────────────────────
    const getDisplayTitle = () => {
        if (!threadId) return query;
        try {
            const threads = JSON.parse(
                localStorage.getItem("corten_threads") || "[]"
            );
            const thread = threads.find((t: any) => t.id === threadId);
            return thread?.title || query;
        } catch {
            return query;
        }
    };

    return (
        <>
            {/* ── Trigger Button ─────────────────────────────────────── */}
            <div className="thread-menu-container" ref={menuRef}>
                <button
                    className={`sp-icon-btn ${open ? "sp-icon-btn--active" : ""}`}
                    onClick={(e) => {
                        e.stopPropagation();
                        setOpen((v) => !v);
                    }}
                    title="More options"
                    aria-label="Thread options"
                    aria-expanded={open}
                    aria-haspopup="menu"
                    suppressHydrationWarning
                >
                    <MoreHorizontal size={15} strokeWidth={2} />
                </button>

                {/* ── Dropdown ──────────────────────────────────────────── */}
                <AnimatePresence>
                    {open && (
                        <motion.div
                            className="tdm-dropdown"
                            role="menu"
                            initial={{ opacity: 0, scale: 0.96, y: -6 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.96, y: -6 }}
                            transition={{ duration: 0.13, ease: [0.16, 1, 0.3, 1] }}
                        >
                            {/* Thread info header */}
                            <div className="tdm-header">
                                <div className="tdm-header-title">{getDisplayTitle()}</div>
                                <div className="tdm-header-meta">
                                    <span>Created by</span>
                                    <span className="tdm-header-username">you</span>
                                    <span className="tdm-dot">·</span>
                                    <span>Today</span>
                                </div>
                            </div>

                            <div className="tdm-section">
                                <button
                                    className="tdm-item"
                                    role="menuitem"
                                    onClick={handleBookmark}
                                >
                                    {bookmarkFeedback ? (
                                        <Check size={14} strokeWidth={2} className="tdm-icon-success" />
                                    ) : (
                                        <Bookmark
                                            size={14}
                                            strokeWidth={1.75}
                                            fill={bookmarked ? "currentColor" : "none"}
                                            className={bookmarked ? "tdm-icon-active" : ""}
                                        />
                                    )}
                                    <span>{bookmarked ? "Remove Bookmark" : "Add Bookmark"}</span>
                                </button>

                                <button
                                    className="tdm-item"
                                    role="menuitem"
                                    onClick={handleAddToSpace}
                                >
                                    <FolderPlus size={14} strokeWidth={1.75} />
                                    <span>Add to Space</span>
                                </button>

                                <button
                                    className="tdm-item"
                                    role="menuitem"
                                    onClick={handleRenameOpen}
                                    disabled={!threadId}
                                >
                                    <Pencil size={14} strokeWidth={1.75} />
                                    <span>Rename Thread</span>
                                </button>
                            </div>

                            <div className="tdm-divider" />

                            <div className="tdm-section">
                                <button
                                    className="tdm-item"
                                    role="menuitem"
                                    onClick={handleExportPDF}
                                >
                                    <FileText size={14} strokeWidth={1.75} />
                                    <span>Export as PDF</span>
                                </button>

                                <button
                                    className="tdm-item"
                                    role="menuitem"
                                    onClick={handleExportMarkdown}
                                >
                                    <FileCode2 size={14} strokeWidth={1.75} />
                                    <span>Export as Markdown</span>
                                </button>

                                <button
                                    className="tdm-item"
                                    role="menuitem"
                                    onClick={handleExportDocx}
                                >
                                    <FileDown size={14} strokeWidth={1.75} />
                                    <span>Export as DOCX</span>
                                </button>
                            </div>

                            <div className="tdm-divider" />

                            <div className="tdm-section">
                                <button
                                    className="tdm-item tdm-item--danger"
                                    role="menuitem"
                                    onClick={() => {
                                        setOpen(false);
                                        setShowDeleteModal(true);
                                    }}
                                    disabled={!threadId}
                                >
                                    <Trash2 size={14} strokeWidth={1.75} />
                                    <span>Delete</span>
                                </button>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* ── Rename Modal ───────────────────────────────────────────── */}
            <AnimatePresence>
                {showRename && (
                    <motion.div
                        className="tdm-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        onClick={() => setShowRename(false)}
                    >
                        <motion.div
                            className="tdm-modal"
                            initial={{ opacity: 0, scale: 0.96, y: 8 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.96, y: 8 }}
                            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h3 className="tdm-modal-title">Rename Thread</h3>
                            <input
                                ref={renameInputRef}
                                className="tdm-modal-input"
                                value={renameValue}
                                onChange={(e) => setRenameValue(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") handleRenameSave();
                                    if (e.key === "Escape") setShowRename(false);
                                }}
                                placeholder="Thread title..."
                                maxLength={120}
                                suppressHydrationWarning
                            />
                            <div className="tdm-modal-actions">
                                <button
                                    className="tdm-modal-btn tdm-modal-btn--cancel"
                                    onClick={() => setShowRename(false)}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="tdm-modal-btn tdm-modal-btn--save"
                                    onClick={handleRenameSave}
                                    disabled={!renameValue.trim()}
                                >
                                    Save
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Delete Confirmation Modal ──────────────────────────────── */}
            <AnimatePresence>
                {showDeleteModal && (
                    <motion.div
                        className="tdm-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        onClick={() => setShowDeleteModal(false)}
                    >
                        <motion.div
                            className="tdm-modal"
                            initial={{ opacity: 0, scale: 0.96, y: 8 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.96, y: 8 }}
                            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <h3 className="tdm-modal-title">Delete thread?</h3>
                            <p className="tdm-modal-msg">
                                This will permanently delete{" "}
                                <strong>&ldquo;{getDisplayTitle()}&rdquo;</strong> and all its
                                messages.
                            </p>
                            <div className="tdm-modal-actions">
                                <button
                                    className="tdm-modal-btn tdm-modal-btn--cancel"
                                    onClick={() => setShowDeleteModal(false)}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="tdm-modal-btn tdm-modal-btn--delete"
                                    onClick={handleDeleteConfirm}
                                >
                                    Delete
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Add to Space Toast ─────────────────────────────────────── */}
            <AnimatePresence>
                {showSpaceToast && (
                    <motion.div
                        className="tdm-toast"
                        initial={{ opacity: 0, y: 16, scale: 0.96 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 8, scale: 0.96 }}
                        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                    >
                        <FolderPlus size={14} strokeWidth={1.75} />
                        <span>Spaces coming soon</span>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}
