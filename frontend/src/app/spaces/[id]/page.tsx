"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import {
    ChevronRight, Lock, Globe, Upload, LinkIcon, Plus, FileText,
    X, ExternalLink, ScrollText, ArrowRight,
    Bookmark, FolderOpen, BookOpen, Briefcase, Code, Lightbulb,
    GraduationCap, Beaker, PenTool, TrendingUp,
    MessageSquare, Edit3, Check, Search, Sparkles
} from "lucide-react";
import { STORAGE_KEYS } from "@/config/constants";

// ── Types ────────────────────────────────────────────────────────────────────

interface LocalSpace {
    id: string;
    name: string;
    description: string;
    icon: string;
    color: string;
    isPrivate: boolean;
    threadIds: string[];
    links: string[];
    instructions: string;
    createdAt: number;
    updatedAt: number;
}

interface ThreadItem {
    id: string;
    title: string;
    query: string;
    answer: string;
    createdAt: number;
    updatedAt: number;
}

const STORAGE_KEY = "corten_spaces";

function getIconComponent(key: string, size = 22) {
    const map: Record<string, React.ReactNode> = {
        bookmark: <Bookmark size={size} />,
        folder: <FolderOpen size={size} />,
        book: <BookOpen size={size} />,
        briefcase: <Briefcase size={size} />,
        code: <Code size={size} />,
        lightbulb: <Lightbulb size={size} />,
        graduation: <GraduationCap size={size} />,
        beaker: <Beaker size={size} />,
        pen: <PenTool size={size} />,
        trending: <TrendingUp size={size} />,
    };
    return map[key] || <Bookmark size={size} />;
}

function formatDate(ts: number): string {
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    if (d.getFullYear() === now.getFullYear()) {
        return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function SpaceDetailPage() {
    const router = useRouter();
    const params = useParams();
    const spaceId = params.id as string;

    const [space, setSpace] = useState<LocalSpace | null>(null);
    const [allSpaces, setAllSpaces] = useState<LocalSpace[]>([]);
    const [threads, setThreads] = useState<ThreadItem[]>([]);
    const [notFound, setNotFound] = useState(false);

    // Editable fields
    const [editingName, setEditingName] = useState(false);
    const [nameValue, setNameValue] = useState("");
    const [editingDesc, setEditingDesc] = useState(false);
    const [descValue, setDescValue] = useState("");

    // Query input
    const [query, setQuery] = useState("");
    const [searchFocused, setSearchFocused] = useState(false);

    // Right panel
    const [showLinkInput, setShowLinkInput] = useState(false);
    const [newLink, setNewLink] = useState("");
    const [showInstructions, setShowInstructions] = useState(false);
    const [instructionsValue, setInstructionsValue] = useState("");

    // Load space + threads
    useEffect(() => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) { setNotFound(true); return; }
            const spaces: LocalSpace[] = JSON.parse(raw);
            setAllSpaces(spaces);
            const found = spaces.find(s => s.id === spaceId);
            if (!found) { setNotFound(true); return; }

            if (!found.links) found.links = [];
            if (!found.instructions) found.instructions = "";

            setSpace(found);
            setNameValue(found.name);
            setDescValue(found.description);
            setInstructionsValue(found.instructions);

            const threadsRaw = localStorage.getItem(STORAGE_KEYS.THREADS);
            if (threadsRaw) {
                const allThreads: ThreadItem[] = JSON.parse(threadsRaw);
                const spaceThreads = allThreads.filter(t => found.threadIds.includes(t.id));
                setThreads(spaceThreads.sort((a, b) => (b.updatedAt || b.createdAt) - (a.updatedAt || a.createdAt)));
            }
        } catch { setNotFound(true); }
    }, [spaceId]);

    const saveSpace = useCallback((updated: LocalSpace) => {
        const newSpaces = allSpaces.map(s => s.id === updated.id ? updated : s);
        setAllSpaces(newSpaces);
        setSpace(updated);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(newSpaces));
    }, [allSpaces]);

    const saveName = () => {
        if (!space || !nameValue.trim()) return;
        saveSpace({ ...space, name: nameValue.trim(), updatedAt: Date.now() });
        setEditingName(false);
    };

    const saveDesc = () => {
        if (!space) return;
        saveSpace({ ...space, description: descValue.trim(), updatedAt: Date.now() });
        setEditingDesc(false);
    };

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (!query.trim() || !space) return;
        router.push(`/search?q=${encodeURIComponent(query)}&space=${space.id}`);
    };

    const addLink = () => {
        if (!space || !newLink.trim()) return;
        let url = newLink.trim();
        if (!url.startsWith("http")) url = "https://" + url;
        const updated = { ...space, links: [...space.links, url], updatedAt: Date.now() };
        saveSpace(updated);
        setNewLink("");
        setShowLinkInput(false);
    };

    const removeLink = (idx: number) => {
        if (!space) return;
        const updated = { ...space, links: space.links.filter((_, i) => i !== idx), updatedAt: Date.now() };
        saveSpace(updated);
    };

    const saveInstructions = () => {
        if (!space) return;
        saveSpace({ ...space, instructions: instructionsValue.trim(), updatedAt: Date.now() });
        setShowInstructions(false);
    };

    const removeThread = (threadId: string) => {
        if (!space) return;
        const updated = { ...space, threadIds: space.threadIds.filter(id => id !== threadId), updatedAt: Date.now() };
        saveSpace(updated);
        setThreads(threads.filter(t => t.id !== threadId));
    };

    // ── Not found ────────────────────────────────────────────────────────────
    if (notFound) {
        return (
            <div className="sd-not-found">
                <div className="sd-not-found-icon"><FolderOpen size={48} strokeWidth={1} /></div>
                <h2>Space not found</h2>
                <p>This space may have been deleted or the link is invalid.</p>
                <Link href="/spaces" className="sd-back-link">
                    <ArrowRight size={14} />
                    Back to Spaces
                </Link>
            </div>
        );
    }

    if (!space) return null;

    return (
        <div className="sd-page">
            {/* ── Hero Section ── */}
            <div className="sd-hero">
                <div className="sd-hero-inner">
                    {/* Breadcrumb */}
                    <div className="sd-breadcrumb">
                        <Link href="/spaces" className="sd-breadcrumb-link">Spaces</Link>
                        <ChevronRight size={13} className="sd-breadcrumb-sep" />
                        <span className="sd-breadcrumb-current">{space.name}</span>
                    </div>

                    {/* Space identity */}
                    <div className="sd-identity">
                        <div className="sd-identity-icon" style={{ background: space.color + "15", color: space.color, boxShadow: `0 0 40px ${space.color}10` }}>
                            {getIconComponent(space.icon, 32)}
                        </div>
                        <div className="sd-identity-info">
                            {editingName ? (
                                <form onSubmit={e => { e.preventDefault(); saveName(); }} className="sd-inline-edit">
                                    <input
                                        autoFocus
                                        className="sd-name-input"
                                        value={nameValue}
                                        onChange={e => setNameValue(e.target.value)}
                                        onBlur={saveName}
                                        onKeyDown={e => e.key === "Escape" && setEditingName(false)}
                                    />
                                </form>
                            ) : (
                                <h1 className="sd-name" onClick={() => setEditingName(true)}>
                                    {space.name}
                                    <Edit3 size={13} className="sd-edit-hint" />
                                </h1>
                            )}
                            {editingDesc ? (
                                <form onSubmit={e => { e.preventDefault(); saveDesc(); }} className="sd-inline-edit">
                                    <input
                                        autoFocus
                                        className="sd-desc-input"
                                        placeholder="Add a description..."
                                        value={descValue}
                                        onChange={e => setDescValue(e.target.value)}
                                        onBlur={saveDesc}
                                        onKeyDown={e => e.key === "Escape" && setEditingDesc(false)}
                                    />
                                </form>
                            ) : (
                                <p className="sd-description" onClick={() => setEditingDesc(true)}>
                                    {space.description || "Add a description..."}
                                </p>
                            )}
                        </div>
                        <div className="sd-identity-badge">
                            {space.isPrivate ? <><Lock size={11} /> Private</> : <><Globe size={11} /> Public</>}
                        </div>
                    </div>

                    {/* Search bar */}
                    <form
                        className={`sd-search ${searchFocused ? "sd-search--focused" : ""}`}
                        onSubmit={handleSearch}
                    >
                        <Search size={18} className="sd-search-icon" />
                        <input
                            type="text"
                            className="sd-search-input"
                            placeholder={`Search within ${space.name}...`}
                            value={query}
                            onChange={e => setQuery(e.target.value)}
                            onFocus={() => setSearchFocused(true)}
                            onBlur={() => setSearchFocused(false)}
                        />
                        <button type="submit" className="sd-search-btn" disabled={!query.trim()}>
                            <ArrowRight size={16} />
                        </button>
                    </form>
                </div>
            </div>

            {/* ── Content Area ── */}
            <div className="sd-content">
                <div className="sd-content-inner">
                    {/* ── Left: Threads ── */}
                    <div className="sd-main">
                        <div className="sd-section-label">
                            <MessageSquare size={14} />
                            <span>Threads</span>
                            {threads.length > 0 && <span className="sd-count">{threads.length}</span>}
                        </div>

                        {threads.length === 0 ? (
                            <div className="sd-empty">
                                <div className="sd-empty-glow" style={{ background: space.color + "08" }} />
                                <Sparkles size={20} style={{ color: space.color, opacity: 0.5 }} />
                                <p>No threads yet</p>
                                <span>Use the search bar above to start your first thread in this space.</span>
                            </div>
                        ) : (
                            <div className="sd-threads">
                                {threads.map(thread => (
                                    <div key={thread.id} className="sd-thread">
                                        <Link
                                            href={`/search?q=${encodeURIComponent(thread.query)}&id=${thread.id}`}
                                            className="sd-thread-link"
                                        >
                                            <div className="sd-thread-dot" style={{ background: space.color }} />
                                            <div className="sd-thread-body">
                                                <span className="sd-thread-title">{thread.title || thread.query}</span>
                                                <span className="sd-thread-meta">{formatDate(thread.updatedAt || thread.createdAt)}</span>
                                            </div>
                                            <ArrowRight size={14} className="sd-thread-arrow" />
                                        </Link>
                                        <button className="sd-thread-remove" onClick={() => removeThread(thread.id)} title="Remove from space">
                                            <X size={12} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* ── Right: Settings Panel ── */}
                    <aside className="sd-aside">
                        {/* Context Sources */}
                        <div className="sd-card">
                            <div className="sd-card-header">
                                <FileText size={14} />
                                <span>Context Sources</span>
                            </div>
                            <p className="sd-card-desc">Files and data to reference in every search</p>
                            <div className="sd-card-actions">
                                <button className="sd-action-btn">
                                    <Upload size={13} />
                                    <span>Upload files</span>
                                </button>
                                <button className="sd-action-btn">
                                    <FileText size={13} />
                                    <span>Paste text</span>
                                </button>
                            </div>
                        </div>

                        {/* Links */}
                        <div className="sd-card">
                            <div className="sd-card-header">
                                <LinkIcon size={14} />
                                <span>Pinned Links</span>
                            </div>
                            <p className="sd-card-desc">Websites included in every search</p>

                            {space.links.length > 0 && (
                                <div className="sd-links">
                                    {space.links.map((link, idx) => {
                                        let domain = "";
                                        try { domain = new URL(link).hostname.replace("www.", ""); } catch { domain = link; }
                                        return (
                                            <div key={idx} className="sd-link">
                                                <div className="sd-link-favicon">
                                                    <ExternalLink size={10} />
                                                </div>
                                                <span className="sd-link-text">{domain}</span>
                                                <button className="sd-link-x" onClick={() => removeLink(idx)}>
                                                    <X size={10} />
                                                </button>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {showLinkInput ? (
                                <form className="sd-link-form" onSubmit={e => { e.preventDefault(); addLink(); }}>
                                    <input
                                        autoFocus
                                        type="text"
                                        placeholder="Enter URL..."
                                        value={newLink}
                                        onChange={e => setNewLink(e.target.value)}
                                        onKeyDown={e => e.key === "Escape" && setShowLinkInput(false)}
                                        className="sd-link-input"
                                    />
                                    <button type="submit" className="sd-link-ok" disabled={!newLink.trim()}>
                                        <Check size={13} />
                                    </button>
                                </form>
                            ) : (
                                <button className="sd-add-btn" onClick={() => setShowLinkInput(true)}>
                                    <Plus size={13} />
                                    <span>Add link</span>
                                </button>
                            )}
                        </div>

                        {/* Instructions */}
                        <div className="sd-card">
                            <div className="sd-card-header">
                                <ScrollText size={14} />
                                <span>Custom Instructions</span>
                            </div>
                            <p className="sd-card-desc">Rules applied to every query in this space</p>

                            {showInstructions ? (
                                <div className="sd-instr-edit">
                                    <textarea
                                        autoFocus
                                        className="sd-instr-textarea"
                                        placeholder="e.g., 'Always cite academic papers', 'Focus on Python examples'..."
                                        value={instructionsValue}
                                        onChange={e => setInstructionsValue(e.target.value)}
                                        rows={4}
                                    />
                                    <div className="sd-instr-btns">
                                        <button className="sd-instr-cancel" onClick={() => { setShowInstructions(false); setInstructionsValue(space.instructions); }}>Cancel</button>
                                        <button className="sd-instr-save" onClick={saveInstructions}>Save</button>
                                    </div>
                                </div>
                            ) : space.instructions ? (
                                <div className="sd-instr-preview" onClick={() => setShowInstructions(true)}>
                                    <p>{space.instructions}</p>
                                    <Edit3 size={11} className="sd-instr-edit-icon" />
                                </div>
                            ) : (
                                <button className="sd-add-btn" onClick={() => setShowInstructions(true)}>
                                    <Plus size={13} />
                                    <span>Add instructions</span>
                                </button>
                            )}
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    );
}
