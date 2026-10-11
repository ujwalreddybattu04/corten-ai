"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, X, Pin, PinOff, Edit3, Trash2, MoreHorizontal, MessageSquare, Clock } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { STORAGE_KEYS, EVENTS } from "@/config/constants";

interface ThreadItem {
    id: string;
    title: string;
    query: string;
    answer: string;
    createdAt: number;
    updatedAt: number;
    history?: { query: string; answer: string }[];
    sources?: { url: string; title: string; domain: string }[];
}

interface HistoryModalProps {
    isOpen: boolean;
    onClose: () => void;
}

// ── Time grouping helpers ────────────────────────────────────────────────────

function getDateGroup(timestamp: number): string {
    const now = new Date();
    const date = new Date(timestamp);
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    const isToday = date.toDateString() === now.toDateString();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = date.toDateString() === yesterday.toDateString();

    if (isToday) return "Today";
    if (isYesterday) return "Yesterday";
    if (diffDays < 7) return "This Week";
    if (diffDays < 30) return "This Month";
    if (date.getFullYear() === now.getFullYear()) return "This Year";
    return "Older";
}

function formatDate(timestamp: number): string {
    const date = new Date(timestamp);
    const now = new Date();

    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
        return "Yesterday";
    }

    if (date.getFullYear() === now.getFullYear()) {
        return date.toLocaleDateString([], { month: "short", day: "numeric" });
    }

    return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function stripCitations(text: string): string {
    return text.replace(/\s*\[\d+\]/g, "");
}

// ── Component ────────────────────────────────────────────────────────────────

export default function HistoryModal({ isOpen, onClose }: HistoryModalProps) {
    const router = useRouter();
    const [threads, setThreads] = useState<ThreadItem[]>([]);
    const [pinnedIds, setPinnedIds] = useState<string[]>([]);
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState("");
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const searchRef = useRef<HTMLInputElement>(null);

    // Load threads from localStorage
    const loadData = useCallback(() => {
        try {
            const raw = localStorage.getItem(STORAGE_KEYS.THREADS);
            if (raw) setThreads(JSON.parse(raw));
            const pins = localStorage.getItem(STORAGE_KEYS.PINNED_THREADS);
            if (pins) setPinnedIds(JSON.parse(pins));
        } catch { /* ignore */ }
    }, []);

    useEffect(() => {
        if (isOpen) {
            loadData();
            setSearchQuery("");
            setSelectedId(null);
            setActiveMenuId(null);
            setEditingId(null);
            setDeleteConfirmId(null);
            // Auto-focus search
            setTimeout(() => searchRef.current?.focus(), 100);
        }
    }, [isOpen, loadData]);

    // Close on Escape
    useEffect(() => {
        if (!isOpen) return;
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                if (activeMenuId) setActiveMenuId(null);
                else if (deleteConfirmId) setDeleteConfirmId(null);
                else onClose();
            }
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [isOpen, onClose, activeMenuId, deleteConfirmId]);

    // Close context menu on outside click
    useEffect(() => {
        if (!activeMenuId) return;
        const handler = () => setActiveMenuId(null);
        window.addEventListener("click", handler);
        return () => window.removeEventListener("click", handler);
    }, [activeMenuId]);

    // ── Filtered + grouped threads ───────────────────────────────────────────

    const filteredThreads = useMemo(() => {
        const q = searchQuery.toLowerCase().trim();
        let list = threads;
        if (q) {
            list = threads.filter(t =>
                (t.title || "").toLowerCase().includes(q) ||
                (t.query || "").toLowerCase().includes(q)
            );
        }
        // Sort: pinned first, then by date desc
        return [...list].sort((a, b) => {
            const ap = pinnedIds.includes(a.id);
            const bp = pinnedIds.includes(b.id);
            if (ap && !bp) return -1;
            if (!ap && bp) return 1;
            return (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0);
        });
    }, [threads, pinnedIds, searchQuery]);

    const groupedThreads = useMemo(() => {
        const groups: { label: string; items: ThreadItem[] }[] = [];
        const groupMap = new Map<string, ThreadItem[]>();

        for (const t of filteredThreads) {
            const group = getDateGroup(t.updatedAt || t.createdAt);
            if (!groupMap.has(group)) groupMap.set(group, []);
            groupMap.get(group)!.push(t);
        }

        // Preserve logical order
        const ORDER = ["Today", "Yesterday", "This Week", "This Month", "This Year", "Older"];
        for (const label of ORDER) {
            const items = groupMap.get(label);
            if (items && items.length > 0) groups.push({ label, items });
        }
        return groups;
    }, [filteredThreads]);

    const selectedThread = useMemo(
        () => threads.find(t => t.id === selectedId) || null,
        [threads, selectedId]
    );

    // ── Actions ──────────────────────────────────────────────────────────────

    const openThread = (thread: ThreadItem) => {
        onClose();
        router.push(`/search?q=${encodeURIComponent(thread.query)}&id=${thread.id}`);
    };

    const togglePin = (id: string) => {
        const newPins = pinnedIds.includes(id)
            ? pinnedIds.filter(p => p !== id)
            : [id, ...pinnedIds];
        setPinnedIds(newPins);
        localStorage.setItem(STORAGE_KEYS.PINNED_THREADS, JSON.stringify(newPins));
        setActiveMenuId(null);
    };

    const startRename = (t: ThreadItem) => {
        setEditingId(t.id);
        setEditingTitle(t.title || t.query);
        setActiveMenuId(null);
    };

    const saveRename = () => {
        if (!editingId || !editingTitle.trim()) return;
        const updated = threads.map(t =>
            t.id === editingId ? { ...t, title: editingTitle.trim() } : t
        );
        setThreads(updated);
        localStorage.setItem(STORAGE_KEYS.THREADS, JSON.stringify(updated));
        window.dispatchEvent(new Event(EVENTS.THREADS_UPDATED));
        setEditingId(null);
        setEditingTitle("");
    };

    const confirmDelete = (id: string) => {
        const updated = threads.filter(t => t.id !== id);
        setThreads(updated);
        localStorage.setItem(STORAGE_KEYS.THREADS, JSON.stringify(updated));

        const updatedPins = pinnedIds.filter(p => p !== id);
        setPinnedIds(updatedPins);
        localStorage.setItem(STORAGE_KEYS.PINNED_THREADS, JSON.stringify(updatedPins));

        window.dispatchEvent(new Event(EVENTS.THREADS_UPDATED));

        if (selectedId === id) setSelectedId(null);
        setDeleteConfirmId(null);
    };

    if (!isOpen) return null;

    return (
        <div className="hm-overlay" onClick={onClose}>
            <div className="hm-container" onClick={e => e.stopPropagation()}>
                {/* ── LEFT PANEL: Search + Thread List ── */}
                <div className="hm-left">
                    {/* Search bar */}
                    <div className="hm-search">
                        <Search size={16} className="hm-search-icon" />
                        <input
                            ref={searchRef}
                            type="text"
                            className="hm-search-input"
                            placeholder="Search..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                        />
                        {searchQuery && (
                            <button className="hm-search-clear" onClick={() => setSearchQuery("")}>
                                <X size={14} />
                            </button>
                        )}
                    </div>

                    {/* Actions section */}
                    <div className="hm-actions-section">
                        <div className="hm-section-header">
                            <span className="hm-section-label">Actions</span>
                        </div>
                        <button
                            className="hm-action-btn"
                            onClick={() => { onClose(); router.push("/"); }}
                        >
                            <span className="hm-action-icon">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" x2="12" y1="5" y2="19" /><line x1="5" x2="19" y1="12" y2="12" /></svg>
                            </span>
                            Create New Thread
                        </button>
                    </div>

                    {/* Thread list */}
                    <div className="hm-thread-list">
                        {groupedThreads.length === 0 ? (
                            <div className="hm-empty">
                                {searchQuery ? "No matching conversations" : "No conversations yet"}
                            </div>
                        ) : (
                            groupedThreads.map(group => (
                                <div key={group.label} className="hm-group">
                                    <div className="hm-group-label">{group.label}</div>
                                    {group.items.map(thread => (
                                        <div key={thread.id} className="hm-thread-wrapper">
                                            {editingId === thread.id ? (
                                                <form
                                                    className="hm-rename-form"
                                                    onSubmit={e => { e.preventDefault(); saveRename(); }}
                                                >
                                                    <input
                                                        autoFocus
                                                        className="hm-rename-input"
                                                        value={editingTitle}
                                                        onChange={e => setEditingTitle(e.target.value)}
                                                        onBlur={saveRename}
                                                        onKeyDown={e => e.key === "Escape" && setEditingId(null)}
                                                    />
                                                </form>
                                            ) : (
                                                <div
                                                    className={`hm-thread-item ${selectedId === thread.id ? "selected" : ""}`}
                                                    onClick={() => setSelectedId(thread.id)}
                                                    onDoubleClick={() => openThread(thread)}
                                                    role="button"
                                                    tabIndex={0}
                                                >
                                                    <div className="hm-thread-left">
                                                        {pinnedIds.includes(thread.id) && (
                                                            <Pin size={12} className="hm-thread-pin" fill="currentColor" />
                                                        )}
                                                        <span className="hm-thread-title">
                                                            {thread.title || thread.query}
                                                        </span>
                                                    </div>
                                                    <div className="hm-thread-right">
                                                        <span className="hm-thread-date">
                                                            {formatDate(thread.updatedAt || thread.createdAt)}
                                                        </span>
                                                        <button
                                                            className="hm-thread-menu-btn"
                                                            onClick={e => {
                                                                e.stopPropagation();
                                                                setActiveMenuId(activeMenuId === thread.id ? null : thread.id);
                                                            }}
                                                        >
                                                            <MoreHorizontal size={14} />
                                                        </button>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Context menu */}
                                            {activeMenuId === thread.id && (
                                                <div className="hm-context-menu" onClick={e => e.stopPropagation()}>
                                                    <button className="hm-menu-item" onClick={() => startRename(thread)}>
                                                        <Edit3 size={13} /> Rename
                                                    </button>
                                                    <button className="hm-menu-item" onClick={() => togglePin(thread.id)}>
                                                        {pinnedIds.includes(thread.id) ? (
                                                            <><PinOff size={13} /> Unpin</>
                                                        ) : (
                                                            <><Pin size={13} /> Pin</>
                                                        )}
                                                    </button>
                                                    <div className="hm-menu-divider" />
                                                    <button
                                                        className="hm-menu-item hm-menu-item--danger"
                                                        onClick={() => { setDeleteConfirmId(thread.id); setActiveMenuId(null); }}
                                                    >
                                                        <Trash2 size={13} /> Delete
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* ── RIGHT PANEL: Preview ── */}
                <div className="hm-right">
                    {selectedThread ? (
                        <div className="hm-preview">
                            <div className="hm-preview-header">
                                <h2 className="hm-preview-title">{selectedThread.title || selectedThread.query}</h2>
                                <div className="hm-preview-meta">
                                    <Clock size={12} />
                                    <span>{new Date(selectedThread.createdAt).toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" })}</span>
                                    {selectedThread.history && selectedThread.history.length > 0 && (
                                        <>
                                            <span className="hm-preview-dot" />
                                            <MessageSquare size={12} />
                                            <span>{selectedThread.history.length + 1} messages</span>
                                        </>
                                    )}
                                </div>
                            </div>

                            <div className="hm-preview-content">
                                {/* Original query + answer */}
                                <div className="hm-preview-turn">
                                    <div className="hm-preview-query">{selectedThread.query}</div>
                                    <div className="hm-preview-answer">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {stripCitations(selectedThread.answer || "")}
                                        </ReactMarkdown>
                                    </div>
                                </div>

                                {/* Follow-up turns */}
                                {selectedThread.history?.map((turn, idx) => (
                                    <div key={idx} className="hm-preview-turn">
                                        <div className="hm-preview-query">{turn.query}</div>
                                        <div className="hm-preview-answer">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {stripCitations(turn.answer || "")}
                                            </ReactMarkdown>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div className="hm-preview-actions">
                                <button className="hm-preview-open" onClick={() => openThread(selectedThread)}>
                                    Open conversation
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="hm-preview-empty">
                            <MessageSquare size={32} strokeWidth={1} />
                            <span>Select a conversation to preview</span>
                        </div>
                    )}
                </div>

                {/* Close button */}
                <button className="hm-close" onClick={onClose}>
                    <X size={18} />
                </button>
            </div>

            {/* Delete confirmation overlay */}
            {deleteConfirmId && (
                <div className="hm-delete-overlay" onClick={() => setDeleteConfirmId(null)}>
                    <div className="hm-delete-modal" onClick={e => e.stopPropagation()}>
                        <h3>Delete conversation?</h3>
                        <p>This action cannot be undone.</p>
                        <div className="hm-delete-actions">
                            <button className="hm-delete-cancel" onClick={() => setDeleteConfirmId(null)}>Cancel</button>
                            <button className="hm-delete-confirm" onClick={() => confirmDelete(deleteConfirmId)}>Delete</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
