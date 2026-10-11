"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import Link from "next/link";
import {
    Search, Plus, MoreHorizontal, Edit3, Trash2, Lock, Globe,
    BookOpen, Briefcase, Code, Lightbulb, GraduationCap, Bookmark,
    FolderOpen, Beaker, PenTool, TrendingUp, X, LayoutGrid,
    MessageSquare
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

const STORAGE_KEY = "corten_spaces";

// ── Icon registry ────────────────────────────────────────────────────────────

const SPACE_ICONS: { key: string; icon: React.ReactNode; label: string }[] = [
    { key: "bookmark", icon: <Bookmark size={22} />, label: "Bookmark" },
    { key: "folder", icon: <FolderOpen size={22} />, label: "Folder" },
    { key: "book", icon: <BookOpen size={22} />, label: "Research" },
    { key: "briefcase", icon: <Briefcase size={22} />, label: "Work" },
    { key: "code", icon: <Code size={22} />, label: "Code" },
    { key: "lightbulb", icon: <Lightbulb size={22} />, label: "Ideas" },
    { key: "graduation", icon: <GraduationCap size={22} />, label: "Learning" },
    { key: "beaker", icon: <Beaker size={22} />, label: "Science" },
    { key: "pen", icon: <PenTool size={22} />, label: "Writing" },
    { key: "trending", icon: <TrendingUp size={22} />, label: "Finance" },
];

const SPACE_COLORS = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
    "#f97316", "#eab308", "#22c55e", "#14b8a6",
    "#06b6d4", "#3b82f6",
];

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

function generateId() {
    return "sp_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

function formatDate(ts: number): string {
    const d = new Date(ts);
    const now = new Date();
    if (d.getFullYear() === now.getFullYear()) {
        return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function SpacesPage() {
    const [spaces, setSpaces] = useState<LocalSpace[]>([]);
    const [searchQuery, setSearchQuery] = useState("");
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
    const [deleteId, setDeleteId] = useState<string | null>(null);
    const [editingSpace, setEditingSpace] = useState<LocalSpace | null>(null);

    // Load spaces
    useEffect(() => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) setSpaces(JSON.parse(raw));
        } catch { /* ignore */ }
    }, []);

    const saveSpaces = useCallback((updated: LocalSpace[]) => {
        setSpaces(updated);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    }, []);

    // Get thread count for each space
    const threadCounts = useMemo(() => {
        const counts: Record<string, number> = {};
        try {
            const raw = localStorage.getItem(STORAGE_KEYS.THREADS);
            if (!raw) return counts;
            JSON.parse(raw);
            for (const space of spaces) {
                counts[space.id] = space.threadIds?.length || 0;
            }
        } catch { /* ignore */ }
        return counts;
    }, [spaces]);

    // Filter
    const filtered = useMemo(() => {
        if (!searchQuery.trim()) return spaces;
        const q = searchQuery.toLowerCase();
        return spaces.filter(s =>
            s.name.toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q)
        );
    }, [spaces, searchQuery]);

    // Actions
    const handleCreate = (data: { name: string; description: string; icon: string; color: string; isPrivate: boolean }) => {
        const newSpace: LocalSpace = {
            id: generateId(),
            name: data.name,
            description: data.description,
            icon: data.icon,
            color: data.color,
            isPrivate: data.isPrivate,
            threadIds: [],
            links: [],
            instructions: "",
            createdAt: Date.now(),
            updatedAt: Date.now(),
        };
        saveSpaces([newSpace, ...spaces]);
        setShowCreateModal(false);
    };

    const handleEdit = (data: { name: string; description: string; icon: string; color: string; isPrivate: boolean }) => {
        if (!editingSpace) return;
        const updated = spaces.map(s =>
            s.id === editingSpace.id
                ? { ...s, name: data.name, description: data.description, icon: data.icon, color: data.color, isPrivate: data.isPrivate, updatedAt: Date.now() }
                : s
        );
        saveSpaces(updated);
        setEditingSpace(null);
    };

    const handleDelete = () => {
        if (!deleteId) return;
        saveSpaces(spaces.filter(s => s.id !== deleteId));
        setDeleteId(null);
    };

    // Close menus on outside click
    useEffect(() => {
        if (!activeMenuId) return;
        const handler = () => setActiveMenuId(null);
        window.addEventListener("click", handler);
        return () => window.removeEventListener("click", handler);
    }, [activeMenuId]);

    return (
        <div className="sp-spaces-page">
            {/* ── Header ── */}
            <div className="sp-spaces-header">
                <h1 className="sp-spaces-title">Spaces</h1>
                <div className="sp-spaces-search-wrap">
                    <Search size={15} className="sp-spaces-search-icon" />
                    <input
                        type="text"
                        className="sp-spaces-search"
                        placeholder="Search Spaces"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                    />
                </div>
                <div className="sp-spaces-header-actions">
                    <Link href="/spaces/templates" className="sp-spaces-tpl-btn">
                        <LayoutGrid size={14} />
                        <span>Templates</span>
                    </Link>
                    <button className="sp-spaces-create-btn" onClick={() => setShowCreateModal(true)}>
                        <Plus size={16} />
                        <span>New Space</span>
                    </button>
                </div>
            </div>

            {/* ── Body ── */}
            <div className="sp-spaces-body">
                {/* ── My Spaces ── */}
                {spaces.length === 0 ? (
                    <div className="sp-spaces-empty">
                        <div className="sp-spaces-empty-icon">
                            <FolderOpen size={40} strokeWidth={1} />
                        </div>
                        <h2>Organize your research</h2>
                        <p>Create spaces to group threads by topic, project, or team. Keep your work structured and easy to find.</p>
                        <button className="sp-spaces-empty-btn" onClick={() => setShowCreateModal(true)}>
                            <Plus size={16} /> Create your first space
                        </button>
                    </div>
                ) : (
                    <>
                        <div className="sp-spaces-section">
                            <h2 className="sp-spaces-section-title">My Spaces</h2>
                            <div className="sp-spaces-grid">
                                {filtered.map(space => (
                                    <div key={space.id} className="sp-space-card-wrap">
                                        <Link href={`/spaces/${space.id}`} className="sp-space-card">
                                            <div className="sp-space-card-icon" style={{ background: space.color + "18", color: space.color }}>
                                                {getIconComponent(space.icon, 24)}
                                            </div>
                                            <div className="sp-space-card-body">
                                                <h3 className="sp-space-card-name">{space.name}</h3>
                                                {space.description && (
                                                    <p className="sp-space-card-desc">{space.description}</p>
                                                )}
                                            </div>
                                            <div className="sp-space-card-footer">
                                                <div className="sp-space-card-meta">
                                                    <span className="sp-space-card-date">{formatDate(space.createdAt)}</span>
                                                    <span className="sp-space-card-badge">
                                                        {space.isPrivate ? <><Lock size={10} /> Private</> : <><Globe size={10} /> Public</>}
                                                    </span>
                                                </div>
                                                <div className="sp-space-card-stats">
                                                    <span><MessageSquare size={11} /> {threadCounts[space.id] || 0}</span>
                                                </div>
                                            </div>
                                        </Link>

                                        {/* Menu button */}
                                        <button
                                            className="sp-space-card-menu"
                                            onClick={e => {
                                                e.preventDefault();
                                                e.stopPropagation();
                                                setActiveMenuId(activeMenuId === space.id ? null : space.id);
                                            }}
                                        >
                                            <MoreHorizontal size={16} />
                                        </button>

                                        {activeMenuId === space.id && (
                                            <div className="sp-space-ctx" onClick={e => e.stopPropagation()}>
                                                <button className="sp-space-ctx-item" onClick={() => { setEditingSpace(space); setActiveMenuId(null); }}>
                                                    <Edit3 size={13} /> Edit
                                                </button>
                                                <div className="sp-space-ctx-divider" />
                                                <button className="sp-space-ctx-item sp-space-ctx-danger" onClick={() => { setDeleteId(space.id); setActiveMenuId(null); }}>
                                                    <Trash2 size={13} /> Delete
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                ))}

                                {/* Add new card */}
                                <button className="sp-space-card sp-space-card--add" onClick={() => setShowCreateModal(true)}>
                                    <Plus size={24} strokeWidth={1.5} />
                                    <span>New Space</span>
                                </button>
                            </div>
                        </div>

                        {filtered.length === 0 && searchQuery && (
                            <div className="sp-spaces-no-results">No spaces matching &ldquo;{searchQuery}&rdquo;</div>
                        )}
                    </>
                )}
            </div>

            {/* ── Create / Edit Modal ── */}
            {(showCreateModal || editingSpace) && (
                <SpaceFormModal
                    initial={editingSpace || undefined}
                    onSave={editingSpace ? handleEdit : handleCreate}
                    onClose={() => { setShowCreateModal(false); setEditingSpace(null); }}
                />
            )}

            {/* ── Delete Confirm ── */}
            {deleteId && (
                <div className="sp-spaces-overlay" onClick={() => setDeleteId(null)}>
                    <div className="sp-spaces-delete-modal" onClick={e => e.stopPropagation()}>
                        <h3>Delete space?</h3>
                        <p>Threads inside this space won&apos;t be deleted, but they&apos;ll be unorganized.</p>
                        <div className="sp-spaces-delete-actions">
                            <button className="sp-spaces-del-cancel" onClick={() => setDeleteId(null)}>Cancel</button>
                            <button className="sp-spaces-del-confirm" onClick={handleDelete}>Delete</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Create / Edit Modal Component ────────────────────────────────────────────

function SpaceFormModal({
    initial,
    onSave,
    onClose,
}: {
    initial?: LocalSpace;
    onSave: (data: { name: string; description: string; icon: string; color: string; isPrivate: boolean }) => void;
    onClose: () => void;
}) {
    const [name, setName] = useState(initial?.name || "");
    const [description, setDescription] = useState(initial?.description || "");
    const [icon, setIcon] = useState(initial?.icon || "bookmark");
    const [color, setColor] = useState(initial?.color || SPACE_COLORS[0]);
    const [isPrivate, setIsPrivate] = useState(initial?.isPrivate ?? true);

    const canSave = name.trim().length > 0;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!canSave) return;
        onSave({ name: name.trim(), description: description.trim(), icon, color, isPrivate });
    };

    return (
        <div className="sp-spaces-overlay" onClick={onClose}>
            <div className="sp-spaces-form-modal" onClick={e => e.stopPropagation()}>
                <div className="sp-spaces-form-header">
                    <h2>{initial ? "Edit Space" : "Create New Space"}</h2>
                    <button className="sp-spaces-form-close" onClick={onClose}>
                        <X size={18} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="sp-spaces-form">
                    {/* Preview */}
                    <div className="sp-spaces-form-preview">
                        <div className="sp-spaces-form-preview-icon" style={{ background: color + "20", color }}>
                            {getIconComponent(icon, 28)}
                        </div>
                        <span className="sp-spaces-form-preview-name">{name || "Untitled Space"}</span>
                    </div>

                    {/* Name */}
                    <div className="sp-spaces-form-field">
                        <label>Name</label>
                        <input
                            autoFocus
                            type="text"
                            placeholder="e.g., AI Research, Project Alpha"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            maxLength={100}
                        />
                    </div>

                    {/* Description */}
                    <div className="sp-spaces-form-field">
                        <label>Description <span className="sp-form-optional">optional</span></label>
                        <textarea
                            placeholder="What is this space about?"
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            rows={2}
                            maxLength={300}
                        />
                    </div>

                    {/* Icon picker */}
                    <div className="sp-spaces-form-field">
                        <label>Icon</label>
                        <div className="sp-spaces-icon-grid">
                            {SPACE_ICONS.map(item => (
                                <button
                                    key={item.key}
                                    type="button"
                                    className={`sp-spaces-icon-btn ${icon === item.key ? "active" : ""}`}
                                    style={icon === item.key ? { background: color + "20", color } : undefined}
                                    onClick={() => setIcon(item.key)}
                                    title={item.label}
                                >
                                    {item.icon}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Color picker */}
                    <div className="sp-spaces-form-field">
                        <label>Color</label>
                        <div className="sp-spaces-color-grid">
                            {SPACE_COLORS.map(c => (
                                <button
                                    key={c}
                                    type="button"
                                    className={`sp-spaces-color-btn ${color === c ? "active" : ""}`}
                                    style={{ background: c }}
                                    onClick={() => setColor(c)}
                                />
                            ))}
                        </div>
                    </div>

                    {/* Privacy */}
                    <div className="sp-spaces-form-field">
                        <label>Visibility</label>
                        <div className="sp-spaces-privacy-toggle">
                            <button
                                type="button"
                                className={`sp-spaces-privacy-btn ${isPrivate ? "active" : ""}`}
                                onClick={() => setIsPrivate(true)}
                            >
                                <Lock size={13} /> Private
                            </button>
                            <button
                                type="button"
                                className={`sp-spaces-privacy-btn ${!isPrivate ? "active" : ""}`}
                                onClick={() => setIsPrivate(false)}
                            >
                                <Globe size={13} /> Public
                            </button>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="sp-spaces-form-actions">
                        <button type="button" className="sp-spaces-form-cancel" onClick={onClose}>Cancel</button>
                        <button type="submit" className="sp-spaces-form-submit" disabled={!canSave}>
                            {initial ? "Save Changes" : "Create Space"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
