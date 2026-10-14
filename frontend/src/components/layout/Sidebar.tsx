"use client";
import { accountStorage } from "@/lib/accountStorage";
import { pharmaThreadPath } from "@/lib/pharmaResearch";


import { useState, useEffect, useMemo, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Pin, ChevronDown, ChartNoAxesCombined, UserRound, LogOut, LogIn } from "lucide-react";
import { STORAGE_KEYS, EVENTS } from "@/config/constants";
import HistoryModal from "./HistoryModal";
import { refreshThreadTitles } from "@/lib/threadTitles";
import { useAuth } from "@/contexts/AuthContext";
import { useModalFocus } from "@/hooks/useModalFocus";

const SIDEBAR_HISTORY_LIMIT = 7;

const NAV_ITEMS = [
    {
        href: "/",
        label: "Search",
        icon: (
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.3-4.3" />
            </svg>
        ),
    },
    {
        href: "/discover",
        label: "Discover",
        icon: (
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
            </svg>
        ),
    },
    {
        href: "/analyst-workspace",
        label: "Analyst Workspace",
        icon: <ChartNoAxesCombined size={20} />,
    },
    {
        href: "/spaces",
        label: "Spaces",
        icon: (
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                <circle cx="9" cy="9" r="2" />
                <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
            </svg>
        ),
    },
];

export default function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const activeThreadId = searchParams.get("id");
    const { user, requestLogout, sessionError, reloadSession } = useAuth();
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [isMobileOpen, setIsMobileOpen] = useState(false);
    const [isMobile, setIsMobile] = useState(false);
    const drawer = useRef<HTMLElement>(null);
    const compact = isCollapsed && !isMobile;
    useModalFocus(drawer, isMobile && isMobileOpen, () => setIsMobileOpen(false));
    const [threads, setThreads] = useState<any[]>([]);
    const [pinnedThreadIds, setPinnedThreadIds] = useState<string[]>([]);
    const [historyOpen, setHistoryOpen] = useState(true);
    const [historyModalOpen, setHistoryModalOpen] = useState(false);

    useEffect(() => {
        const media = window.matchMedia("(max-width: 768px)");
        const update = () => { setIsMobile(media.matches); setIsMobileOpen(false); };
        update();
        media.addEventListener("change", update);
        return () => media.removeEventListener("change", update);
    }, []);

    useEffect(() => {
        if (!isMobile || !isMobileOpen) return;
        const previous = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => { document.body.style.overflow = previous; };
    }, [isMobile, isMobileOpen]);

    useEffect(() => { setIsMobileOpen(false); }, [pathname, activeThreadId]);

    const loadThreads = () => {
        if (typeof window === "undefined") return;
        try {
            let threadsJson = accountStorage.getItem(STORAGE_KEYS.THREADS);
            if (!threadsJson) {
                threadsJson = accountStorage.getItem("orivanta_threads");
                if (threadsJson) accountStorage.setItem(STORAGE_KEYS.THREADS, threadsJson);
            }
            setThreads(threadsJson ? refreshThreadTitles(SIDEBAR_HISTORY_LIMIT) : []);

            let pinsJson = accountStorage.getItem(STORAGE_KEYS.PINNED_THREADS);
            if (!pinsJson) {
                pinsJson = accountStorage.getItem("orivanta_pinned_threads");
                if (pinsJson) accountStorage.setItem(STORAGE_KEYS.PINNED_THREADS, pinsJson);
            }
            setPinnedThreadIds(pinsJson ? JSON.parse(pinsJson) : []);
        } catch (e) {
            console.error("Failed to load threads", e);
        }
    };

    useEffect(() => {
        loadThreads();
        window.addEventListener(EVENTS.THREADS_UPDATED, loadThreads);
        return () => window.removeEventListener(EVENTS.THREADS_UPDATED, loadThreads);
    }, []);

    useEffect(() => {
        if (typeof window !== "undefined") {
            document.documentElement.style.setProperty("--sidebar-width", isCollapsed ? "72px" : "240px");
        }
    }, [isCollapsed]);

    // Sort: pinned first, then by updatedAt desc
    const sortedThreads = useMemo(() => {
        return [...threads].sort((a, b) => {
            const aPinned = pinnedThreadIds.includes(a.id);
            const bPinned = pinnedThreadIds.includes(b.id);
            if (aPinned && !bPinned) return -1;
            if (!aPinned && bPinned) return 1;
            return (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0);
        });
    }, [threads, pinnedThreadIds]);

    const recentThreads = sortedThreads.slice(0, SIDEBAR_HISTORY_LIMIT);

    return (
        <>
            {/* Mobile Burger */}
            <button className="mobile-menu-toggle" onClick={() => setIsMobileOpen(true)} aria-label="Open menu" aria-expanded={isMobileOpen} aria-controls="main-sidebar" suppressHydrationWarning>
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" x2="21" y1="12" y2="12" /><line x1="3" x2="21" y1="6" y2="6" /><line x1="3" x2="21" y1="18" y2="18" /></svg>
            </button>

            {isMobileOpen && <div className="sidebar-backdrop" onClick={() => setIsMobileOpen(false)} />}

            <aside ref={drawer} className={`sidebar ${compact ? "collapsed" : ""} ${isMobileOpen ? "mobile-open" : ""}`} id="main-sidebar" role={isMobile && isMobileOpen ? "dialog" : undefined} aria-modal={isMobile && isMobileOpen ? true : undefined} aria-label="Main navigation" inert={isMobile && !isMobileOpen}>
                {/* Brand */}
                <div className="sidebar-brand">
                    <div className="sidebar-brand-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                        </svg>
                    </div>
                    <span className="sidebar-brand-name">Corten</span>
                    <button className="mobile-close-btn" aria-label="Close menu" onClick={() => setIsMobileOpen(false)} suppressHydrationWarning>
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="6" y1="6" y2="18" /><line x1="6" x2="18" y1="6" y2="18" /></svg>
                    </button>
                </div>

                <div className="sidebar-body">
                    {/* Nav */}
                    <nav className="sidebar-nav" aria-label="App tools">
                        {NAV_ITEMS.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`sidebar-link ${pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href)) ? "active" : ""}`}
                                id={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                                title={compact ? item.label : undefined}
                                aria-label={item.label}
                                aria-current={pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href)) ? "page" : undefined}
                                onClick={() => setIsMobileOpen(false)}
                            >
                                <span className="sidebar-link-icon">{item.icon}</span>
                                <span className="sidebar-link-label">{item.label}</span>
                            </Link>
                        ))}
                    </nav>

                    <div className="sidebar-divider" />

                    {/* New Thread */}
                    <Link href="/" className="sidebar-new-thread" id="new-thread-btn" aria-label="New Thread" title={compact ? "New Thread" : undefined} onClick={() => setIsMobileOpen(false)}>
                        <span className="sidebar-new-thread-icon">
                            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" x2="12" y1="5" y2="19" /><line x1="5" x2="19" y1="12" y2="12" /></svg>
                        </span>
                        <span className="sidebar-link-label">New Thread</span>
                    </Link>

                    {/* ── History Section (Grok-style) ── */}
                    <div className="sidebar-divider" />
                    <div className="sidebar-history" aria-hidden={compact || undefined} inert={compact}>
                        <button
                            className={`sidebar-history-toggle ${historyOpen ? "open" : ""}`}
                            onClick={() => setHistoryOpen(!historyOpen)}
                            aria-expanded={historyOpen}
                            aria-controls="sidebar-history-list"
                            suppressHydrationWarning
                        >
                            <span className="sidebar-history-label">History</span>
                            <ChevronDown size={14} className="sidebar-history-chevron" />
                        </button>

                        {historyOpen && (
                            <div className="sidebar-history-list" id="sidebar-history-list">
                                {recentThreads.length === 0 ? (
                                    <div className="sidebar-history-empty">No conversations yet</div>
                                ) : (
                                    recentThreads.map((thread) => (
                                        <Link
                                            key={thread.id}
                                href={pharmaThreadPath(thread)}
                                            className={`sidebar-history-item ${thread.id === activeThreadId ? "active" : ""}`}
                                            title={thread.title || thread.query}
                                            aria-current={thread.id === activeThreadId ? "page" : undefined}
                                            onClick={() => setIsMobileOpen(false)}
                                        >
                                            {pinnedThreadIds.includes(thread.id) && (
                                                <Pin size={11} className="sidebar-history-pin" fill="currentColor" />
                                            )}
                                            <span className="sidebar-history-text">
                                                {thread.title || thread.query}
                                            </span>
                                        </Link>
                                    ))
                                )}

                                {threads.length > 0 && (
                                    <button
                                        className="sidebar-history-see-all"
                                        onClick={() => setHistoryModalOpen(true)}
                                    >
                                        See all
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="sidebar-footer">
                    {sessionError && <div className="sidebar-session-error" role="alert">{sessionError}<button onClick={() => void reloadSession()}>Retry</button></div>}
                    {user ? <>
                        <Link href="/settings" className="sidebar-link" title={`${user.name}\n${user.email}`} aria-label={`Account settings for ${user.name}`} onClick={() => setIsMobileOpen(false)}>
                            <span className="sidebar-link-icon"><UserRound size={20} /></span>
                            <span className="sidebar-link-label">{user.name}</span>
                        </Link>
                        <button className="sidebar-link" id="sign-out-btn" title="Sign out" aria-label="Sign out" onClick={requestLogout}>
                            <span className="sidebar-link-icon"><LogOut size={20} /></span><span className="sidebar-link-label">Sign out</span>
                        </button>
                    </> : <Link href={`/auth/login?next=${encodeURIComponent(pathname + (searchParams.toString() ? "?" + searchParams.toString() : ""))}`} className="sidebar-link" id="sign-in-btn" title="Sign in">
                        <span className="sidebar-link-icon"><LogIn size={20} /></span><span className="sidebar-link-label">Sign in</span>
                    </Link>}
                    <button
                        onClick={() => setIsCollapsed(!isCollapsed)}
                        className={`sidebar-link sidebar-collapse-btn ${compact ? "collapsed-state" : ""}`}
                        title={compact ? "Expand" : "Collapse"}
                        aria-label={compact ? "Expand sidebar" : "Collapse sidebar"}
                        aria-expanded={!compact}
                        suppressHydrationWarning
                    >
                        <span className="sidebar-link-icon collapse-icon-container">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" /><path d="M9 3v18" /></svg>
                        </span>
                        <span className="sidebar-link-label">Collapse</span>
                    </button>

                    <Link href="/settings" className="sidebar-link" id="nav-settings" aria-label="Settings" title={compact ? "Settings" : undefined} onClick={() => setIsMobileOpen(false)}>
                        <span className="sidebar-link-icon">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
                                <circle cx="12" cy="12" r="3" />
                            </svg>
                        </span>
                        <span className="sidebar-link-label">Settings</span>
                    </Link>
                </div>
            </aside>

            <HistoryModal
                isOpen={historyModalOpen}
                onClose={() => setHistoryModalOpen(false)}
            />
        </>
    );
}
