"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
    Heart, MoreHorizontal, Share2, Newspaper,
    Monitor, TrendingUp, Palette, Trophy, Tv,
    Sun, Cloud, CloudSun, CloudRain, CloudSnow, CloudLightning, Wind, MapPin,
    Sparkles, Bookmark, BookmarkCheck, FolderPlus, ThumbsDown,
} from "lucide-react";
import {
    logInteraction,
    computeAffinities,
    rankArticles,
    readLikedIds,
    readBookmarkedIds,
    readDislikedIds,
    getWeightedFetchSizes,
    liveReRank,
} from "@/lib/personalization";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ArticleSource {
    name: string;
    domain: string;
    favicon: string;
}

interface Article {
    id: string;
    title: string;
    description: string;
    url: string;
    image: string;
    publishedAt: string;
    source: ArticleSource;
    isHero: boolean;
    category?: string; // injected client-side for personalization scoring
}

interface MarketItem {
    price: number;
    change: number;
    change_pct: number;
    symbol: string;
    sparkline: number[];
    is_crypto: boolean;
}

interface MarketData {
    [key: string]: MarketItem;
}

interface ForecastDay {
    date: string;
    max_c: number;
    min_c: number;
    icon: string;
}

interface WeatherData {
    temp_c: number;
    feels_like_c: number;
    humidity: string;
    description: string;
    city: string;
    icon: string;
    high_c?: number;
    low_c?: number;
    forecast: ForecastDay[];
}

interface TrendingStock {
    name: string;
    symbol: string;
    price: number;
    change: number;
    change_pct: number;
    favicon: string;
}

interface SidebarData {
    market: MarketData;
    trending_stocks: TrendingStock[];
    weather: WeatherData;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// All tabs shown inline — no dropdown
const ALL_TABS = [
    { id: "for-you",       label: "For You"        },
    { id: "top",           label: "Top"            },
    { id: "technology",    label: "Tech & Science" },
    { id: "business",      label: "Business"       },
    { id: "entertainment", label: "Arts & Culture" },
    { id: "sports",        label: "Sports"         },
    { id: "health",        label: "Entertainment"  },
] as const;

type TabId = typeof ALL_TABS[number]["id"];

// Sidebar interest pills (separate from tabs)
const TOPIC_OPTIONS = [
    { id: "technology",    label: "Tech & Science", icon: Monitor    },
    { id: "business",      label: "Business",       icon: TrendingUp },
    { id: "entertainment", label: "Arts & Culture", icon: Palette    },
    { id: "sports",        label: "Sports",         icon: Trophy     },
    { id: "health",        label: "Entertainment",  icon: Tv         },
];

const MARKET_ORDER = ["S&P 500", "NASDAQ", "VIX", "Bitcoin"];

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins} minute${mins !== 1 ? "s" : ""} ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hour${hrs !== 1 ? "s" : ""} ago`;
    const days = Math.floor(hrs / 24);
    return `${days} day${days !== 1 ? "s" : ""} ago`;
}

function formatPrice(price: number, isCrypto: boolean): string {
    if (isCrypto) return `$${price.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function dayLabel(dateStr: string, index: number): string {
    if (index === 0) return "Today";
    if (index === 1) return "Tmr";
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", { weekday: "short" });
}

// ── Weather Icon ──────────────────────────────────────────────────────────────

const WEATHER_ICONS: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
    "sunny":         Sun,
    "partly-cloudy": CloudSun,
    "cloudy":        Cloud,
    "fog":           Wind,
    "rain":          CloudRain,
    "snow":          CloudSnow,
    "thunderstorm":  CloudLightning,
};

function WeatherIcon({ code, size = 24, className = "" }: { code: string; size?: number; className?: string }) {
    const Icon = WEATHER_ICONS[code] ?? CloudSun;
    return <Icon size={size} strokeWidth={1.5} className={className} />;
}

// ── Sparkline SVG ─────────────────────────────────────────────────────────────

function Sparkline({ data, isUp }: { data: number[]; isUp: boolean }) {
    if (!data || data.length < 2) {
        // Fallback: simple angled line
        const color = isUp ? "#22c55e" : "#ef4444";
        const y1 = isUp ? 20 : 4;
        const y2 = isUp ? 4 : 20;
        return (
            <svg width="80" height="24" viewBox="0 0 80 24" fill="none" className="discover-sparkline">
                <polyline points={`0,${y1} 80,${y2}`} stroke={color} strokeWidth="1.5" strokeLinecap="round" />
            </svg>
        );
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const W = 80, H = 24, pad = 2;

    const points = data.map((v, i) => {
        const x = pad + (i / (data.length - 1)) * (W - pad * 2);
        const y = H - pad - ((v - min) / range) * (H - pad * 2);
        return `${x},${y}`;
    }).join(" ");

    const color = isUp ? "#22c55e" : "#ef4444";
    const lastX = pad + ((data.length - 1) / (data.length - 1)) * (W - pad * 2);
    const fillPath = `M ${points.split(" ")[0]} L ${points.split(" ").slice(1).join(" L ")} L ${lastX},${H} L ${pad},${H} Z`;

    return (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} fill="none" className="discover-sparkline">
            <path d={fillPath} fill={color} fillOpacity="0.1" />
            <polyline points={points} stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

// ── Article Footer (sources + actions) ───────────────────────────────────────

function ArticleFooter({
    articleId,
    source,
    liked,
    bookmarked,
    disliked,
    menuOpen,
    menuRef,
    onLike,
    onMore,
    onBookmark,
    onAddToSpace,
    onDislike,
}: {
    articleId: string;
    source: ArticleSource;
    liked: boolean;
    bookmarked: boolean;
    disliked: boolean;
    menuOpen: boolean;
    menuRef: React.RefObject<HTMLDivElement | null>;
    onLike: (e: React.MouseEvent) => void;
    onMore: (e: React.MouseEvent) => void;
    onBookmark: (e: React.MouseEvent) => void;
    onAddToSpace: (e: React.MouseEvent) => void;
    onDislike: (e: React.MouseEvent) => void;
}) {
    return (
        <div className="discover-article-footer">
            <div className="discover-sources-row">
                <div className="discover-favicons">
                    {source.favicon && (
                        <div className="discover-favicon-wrap">
                            <img
                                src={source.favicon}
                                alt={source.name}
                                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                            />
                        </div>
                    )}
                </div>
                <span className="discover-source-count">{source.name}</span>
            </div>
            <div className="discover-article-actions">
                <button
                    className={`discover-action-btn ${liked ? "liked" : ""}`}
                    onClick={onLike}
                    title="Like"
                >
                    <Heart size={14} fill={liked ? "currentColor" : "none"} />
                </button>
                <div className="discover-more-wrap" ref={menuOpen ? menuRef : null}>
                    <button
                        className={`discover-action-btn ${menuOpen ? "active" : ""}`}
                        onClick={onMore}
                        title="More"
                    >
                        <MoreHorizontal size={14} />
                    </button>
                    {menuOpen && (
                        <div className="discover-dropdown">
                            <button className={`discover-dropdown-item ${bookmarked ? "active" : ""}`} onClick={onBookmark}>
                                {bookmarked
                                    ? <BookmarkCheck size={14} />
                                    : <Bookmark size={14} />
                                }
                                {bookmarked ? "Bookmarked" : "Bookmark"}
                            </button>
                            <button className="discover-dropdown-item" onClick={onAddToSpace}>
                                <FolderPlus size={14} />
                                Add to Space
                            </button>
                            <button className={`discover-dropdown-item dislike ${disliked ? "active" : ""}`} onClick={onDislike}>
                                <ThumbsDown size={14} />
                                {disliked ? "Disliked" : "Dislike"}
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ── Skeleton Loaders ──────────────────────────────────────────────────────────

function HeroSkeleton() {
    return (
        <div className="discover-hero-skeleton">
            <div className="discover-hero-skeleton-content">
                <div className="skeleton discover-skeleton-line discover-skeleton-title" />
                <div className="skeleton discover-skeleton-line" style={{ width: "70%", height: 22 }} />
                <div className="skeleton discover-skeleton-line" style={{ width: "40%", height: 14 }} />
                <div className="skeleton discover-skeleton-line" style={{ height: 14, marginTop: 8 }} />
                <div className="skeleton discover-skeleton-line" style={{ width: "85%", height: 14 }} />
            </div>
            <div className="skeleton discover-skeleton-img" />
        </div>
    );
}

function GridSkeleton() {
    return (
        <div className="discover-grid">
            {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="discover-card-skeleton">
                    <div className="skeleton discover-card-skeleton-img" />
                    <div className="skeleton discover-skeleton-line" style={{ height: 14 }} />
                    <div className="skeleton discover-skeleton-line" style={{ width: "75%", height: 14 }} />
                    <div className="skeleton discover-skeleton-line" style={{ width: "50%", height: 12 }} />
                </div>
            ))}
        </div>
    );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function DiscoverPage() {
    const router = useRouter();
    const [activeTab, setActiveTab] = useState<TabId>("for-you");
    const [articles, setArticles] = useState<Article[]>([]);
    const [sidebar, setSidebar] = useState<SidebarData | null>(null);
    const [loadingArticles, setLoadingArticles] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [loadingSidebar, setLoadingSidebar] = useState(true);
    const [likedIds, setLikedIds] = useState<Set<string>>(new Set());
    const [bookmarkedIds, setBookmarkedIds] = useState<Set<string>>(new Set());
    const [dislikedIds, setDislikedIds] = useState<Set<string>>(new Set());
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const [showFeedToast, setShowFeedToast] = useState(false);
    const [showInterestsToast, setShowInterestsToast] = useState(false);
    const feedToastShownRef = useRef(false);
    const menuRef = useRef<HTMLDivElement>(null);
    // Always start with static default — avoids SSR/client hydration mismatch.
    // localStorage is synced after mount in useEffect below.
    const [selectedInterests, setSelectedInterests] = useState<string[]>(["technology", "business"]);
    const [interestsSaved, setInterestsSaved] = useState(false);
    const [page, setPage] = useState(1);
    const [hasMore, setHasMore] = useState(true);
    const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(() => {
        // Restore saved GPS coords immediately for accurate weather on load
        if (typeof window !== "undefined") {
            try {
                const saved = localStorage.getItem("user_coords");
                if (saved) {
                    const parsed = JSON.parse(saved);
                    // Expire after 1 hour — user may have moved
                    if (parsed.ts && Date.now() - parsed.ts < 3600000) {
                        return { lat: parsed.lat, lon: parsed.lon };
                    }
                }
            } catch { /* ignore */ }
        }
        return null;
    });
    const sentinelRef = useRef<HTMLDivElement>(null);

    const fetchArticles = useCallback(async (tab: TabId, pageNum: number = 1, append: boolean = false) => {
        if (pageNum === 1) setLoadingArticles(true);
        else setLoadingMore(true);
        try {
            let newArticles: Article[] = [];
            let moreAvailable = false;

            if (tab === "for-you") {
                // All 5 categories — always fetch all for diversity
                const allCategories = ["technology", "business", "entertainment", "sports", "health"];

                // Compute affinities BEFORE fetching so we can weight the request sizes
                const affinities = computeAffinities();

                // Weighted fetch: more articles from liked categories, fewer from disliked
                const fetchSizes = getWeightedFetchSizes(allCategories, affinities, 50);

                const results = await Promise.all(
                    allCategories.map((cat: string) =>
                        fetch(`${API_BASE}/api/v1/discover?category=${cat}&page=${pageNum}&page_size=${fetchSizes[cat] ?? 9}`)
                            .then(r => r.ok ? r.json() : { articles: [], has_more: false, category: cat })
                            .catch(() => ({ articles: [], has_more: false, category: cat }))
                    )
                );

                // Tag each article with its source category for affinity scoring
                let tagged: Article[] = [];
                results.forEach((r, idx) => {
                    const cat = allCategories[idx];
                    (r.articles ?? []).forEach((a: Article) => {
                        tagged.push({ ...a, category: cat });
                    });
                });

                // Deduplicate
                const seen = new Set<string>();
                tagged = tagged.filter(a => seen.has(a.id) ? false : (seen.add(a.id), true));

                // Score + sort + diversity injection
                const disliked = readDislikedIds();
                newArticles = rankArticles(tagged, affinities, disliked);
                moreAvailable = results.some(r => r.has_more);
            } else {
                const res = await fetch(`${API_BASE}/api/v1/discover?category=${tab}&page=${pageNum}&page_size=18`);
                if (!res.ok) throw new Error("Failed");
                const data = await res.json();
                // Tag articles with their category
                newArticles = (data.articles ?? []).map((a: Article) => ({ ...a, category: tab }));
                moreAvailable = data.has_more ?? false;
            }

            setArticles(prev => {
                if (!append) return newArticles;
                const existingIds = new Set(prev.map(a => a.id));
                return [...prev, ...newArticles.filter(a => !existingIds.has(a.id))];
            });
            setHasMore(moreAvailable);
            setPage(pageNum);
        } catch {
            if (!append) setArticles([]);
        } finally {
            setLoadingArticles(false);
            setLoadingMore(false);
        }
    }, []);

    const fetchSidebar = useCallback(async (lat?: number, lon?: number) => {
        setLoadingSidebar(true);
        try {
            const params = lat != null && lon != null ? `?lat=${lat}&lon=${lon}` : "";
            const res = await fetch(`${API_BASE}/api/v1/discover/sidebar${params}`);
            if (!res.ok) throw new Error("Failed");
            const data = await res.json();
            setSidebar(data);
        } catch {
            setSidebar(null);
        } finally {
            setLoadingSidebar(false);
        }
    }, []);

    const saveCoords = (lat: number, lon: number) => {
        setCoords({ lat, lon });
        try {
            localStorage.setItem("user_coords", JSON.stringify({ lat, lon, ts: Date.now() }));
        } catch { /* quota */ }
    };

    const requestLocation = () => {
        setLoadingSidebar(true);
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const { latitude, longitude } = pos.coords;
                saveCoords(latitude, longitude);
                fetchSidebar(latitude, longitude);
            },
            () => {
                // denied — still fetch with IP fallback
                fetchSidebar();
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
        );
    };

    // Close dropdown menu when clicking outside
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setOpenMenuId(null);
            }
        };
        if (openMenuId) document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [openMenuId]);

    // Restore all persisted state from localStorage after hydration (SSR-safe)
    useEffect(() => {
        try {
            const saved = localStorage.getItem("discover_interests");
            if (saved) setSelectedInterests(JSON.parse(saved));
        } catch { /* ignore */ }

        // Restore liked / bookmarked / disliked article IDs from personalization store
        setLikedIds(readLikedIds());
        setBookmarkedIds(readBookmarkedIds());
        setDislikedIds(readDislikedIds());
    }, []);

    // Initial load — use saved GPS coords or try silent geolocation
    useEffect(() => {
        fetchArticles("for-you");

        // 1. If we have saved coords from a previous session, use them immediately
        //    (gives accurate weather on first paint, no delay)
        let savedLat: number | undefined;
        let savedLon: number | undefined;
        try {
            const saved = localStorage.getItem("user_coords");
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed.ts && Date.now() - parsed.ts < 3600000) {
                    savedLat = parsed.lat;
                    savedLon = parsed.lon;
                }
            }
        } catch { /* ignore */ }

        if (savedLat != null && savedLon != null) {
            // Use cached coords for instant accurate weather
            fetchSidebar(savedLat, savedLon);
            // Also refresh GPS in background to keep coords fresh
            if (typeof navigator !== "undefined" && navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (pos) => saveCoords(pos.coords.latitude, pos.coords.longitude),
                    () => {},
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
                );
            }
        } else if (typeof navigator !== "undefined" && navigator.geolocation) {
            navigator.permissions?.query({ name: "geolocation" }).then((perm) => {
                if (perm.state === "granted") {
                    // Already granted — get precise location silently
                    navigator.geolocation.getCurrentPosition(
                        (pos) => {
                            saveCoords(pos.coords.latitude, pos.coords.longitude);
                            fetchSidebar(pos.coords.latitude, pos.coords.longitude);
                        },
                        () => fetchSidebar(),
                        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
                    );
                } else {
                    // Not granted yet — use IP geolocation
                    fetchSidebar();
                }
            }).catch(() => fetchSidebar());
        } else {
            fetchSidebar();
        }
    }, [fetchArticles, fetchSidebar]);

    // Infinite scroll — IntersectionObserver on sentinel div
    useEffect(() => {
        const sentinel = sentinelRef.current;
        if (!sentinel) return;

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting && hasMore && !loadingMore && !loadingArticles) {
                    fetchArticles(activeTab, page + 1, true);
                }
            },
            { rootMargin: "300px" }
        );

        observer.observe(sentinel);
        return () => observer.disconnect();
    }, [hasMore, loadingMore, loadingArticles, activeTab, page, fetchArticles]);

    const handleTabChange = (tab: TabId) => {
        setActiveTab(tab);
        setPage(1);
        setHasMore(true);
        fetchArticles(tab, 1, false);
    };

    const showFeedToastOnce = () => {
        // Only show once ever — check localStorage flag
        if (feedToastShownRef.current) return;
        try {
            if (localStorage.getItem("discover_feed_toast_shown")) return;
        } catch { /* ignore */ }
        feedToastShownRef.current = true;
        setShowFeedToast(true);
        setTimeout(() => setShowFeedToast(false), 4000);
        try { localStorage.setItem("discover_feed_toast_shown", "1"); } catch { /* ignore */ }
    };

    // Handlers receive category directly from the article — avoids stale state lookup
    // Live re-rank: after any explicit interaction on the For You tab,
    // immediately re-sort articles so user sees the effect of their action.
    const applyLiveReRank = useCallback(() => {
        if (activeTab !== "for-you") return;
        setArticles(prev => liveReRank(prev));
    }, [activeTab]);

    const toggleLike = (id: string, category: string, e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const isLiking = !likedIds.has(id);
        logInteraction(id, category, "like", !isLiking);
        setLikedIds(readLikedIds());
        if (isLiking) showFeedToastOnce();
        applyLiveReRank();
    };

    const handleMore = (id: string, e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setOpenMenuId((prev) => (prev === id ? null : id));
    };

    const handleBookmark = (id: string, category: string, e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const isBookmarking = !bookmarkedIds.has(id);
        logInteraction(id, category, "bookmark", !isBookmarking);
        setBookmarkedIds(readBookmarkedIds());
        setOpenMenuId(null);
        applyLiveReRank();
    };

    const handleDislike = (id: string, category: string, e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const isDisliking = !dislikedIds.has(id);
        logInteraction(id, category, "dislike", !isDisliking);
        setDislikedIds(readDislikedIds());
        if (isDisliking) showFeedToastOnce();
        setOpenMenuId(null);
        applyLiveReRank();
    };

    const handleAddToSpace = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setOpenMenuId(null);
        // Spaces feature — coming soon
    };

    const openArticle = (article: Article) => {
        try { sessionStorage.setItem(`discover_article_${article.id}`, JSON.stringify(article)); } catch { /* ignore */ }
        logInteraction(article.id, article.category ?? activeTab, "click");
        router.push(`/discover/article/${article.id}`);
    };

    const handleShare = () => {
        if (navigator.share) {
            navigator.share({ title: "Discover — Corten AI", url: window.location.href });
        } else {
            navigator.clipboard.writeText(window.location.href);
        }
    };

    const toggleInterest = (id: string) => {
        setSelectedInterests((prev) =>
            prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
        );
    };

    const handleSaveInterests = () => {
        localStorage.setItem("discover_interests", JSON.stringify(selectedInterests));
        // Invalidate affinity cache so computeAffinities picks up new interests
        try { localStorage.removeItem("discover_affinities_v3"); } catch { /* ignore */ }
        setInterestsSaved(true);
        setTimeout(() => setInterestsSaved(false), 2000);
        // Show toast popup
        setShowInterestsToast(true);
        setTimeout(() => setShowInterestsToast(false), 3500);
        // Switch to For You and refresh with new interests immediately
        setActiveTab("for-you");
        setPage(1);
        setHasMore(true);
        fetchArticles("for-you");
    };

    const heroArticle = articles[0] ?? null;
    const gridArticles = articles.slice(1);

    return (
        <div className="discover-page">
            {/* ── Interests Saved Toast ── */}
            {showInterestsToast && (
                <div className="discover-feed-toast">
                    <div className="discover-feed-toast-check">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M2.5 7L5.5 10L11.5 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </div>
                    <span>Interests saved! Your For You feed has been updated.</span>
                    <button className="discover-feed-toast-close" onClick={() => setShowInterestsToast(false)}>×</button>
                </div>
            )}

            {/* ── Feed Toast (like/dislike) ── */}
            {showFeedToast && (
                <div className="discover-feed-toast" style={{ top: showInterestsToast ? "116px" : undefined }}>
                    <div className="discover-feed-toast-check">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M2.5 7L5.5 10L11.5 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </div>
                    <span>Liking articles will help personalize your feed</span>
                    <button className="discover-feed-toast-close" onClick={() => setShowFeedToast(false)}>×</button>
                </div>
            )}

            {/* ── Header ── */}
            <div className="discover-header">
                <div className="discover-header-inner">
                    <h1 className="discover-title">Discover</h1>

                    <div className="discover-tabs">
                        {ALL_TABS.map((t) => (
                            <button
                                key={t.id}
                                className={`discover-tab ${activeTab === t.id ? "active" : ""}`}
                                onClick={() => handleTabChange(t.id)}
                            >
                                {t.id === "for-you" && <Sparkles size={11} className="discover-tab-sparkle" />}
                                {t.label}
                            </button>
                        ))}
                    </div>

                    <button className="discover-share-btn" onClick={handleShare}>
                        <Share2 size={13} />
                        Share
                    </button>
                </div>
            </div>

            {/* ── Body ── */}
            <div className="discover-body">
                {/* ── Feed ── */}
                <div className="discover-feed">
                    {loadingArticles ? (
                        <>
                            <HeroSkeleton />
                            <GridSkeleton />
                        </>
                    ) : articles.length === 0 ? (
                        <div className="discover-empty">
                            <div className="discover-empty-icon">
                                <Newspaper size={40} />
                            </div>
                            <p className="discover-empty-text">No articles found. Try a different category.</p>
                        </div>
                    ) : (
                        <>
                            {/* Hero */}
                            {heroArticle && (
                                <a
                                    className="discover-hero"
                                    href={`/discover/article/${heroArticle.id}`}
                                    onClick={(e) => { e.preventDefault(); openArticle(heroArticle); }}
                                >
                                    <div className="discover-hero-content">
                                        <div className="discover-hero-meta">
                                            <span>Published</span>
                                            <span className="discover-hero-meta-dot" />
                                            <span>{timeAgo(heroArticle.publishedAt)}</span>
                                        </div>
                                        <h2 className="discover-hero-title">{heroArticle.title}</h2>
                                        {heroArticle.description && (
                                            <p className="discover-hero-description">{heroArticle.description}</p>
                                        )}
                                        <ArticleFooter
                                            articleId={heroArticle.id}
                                            source={heroArticle.source}
                                            liked={likedIds.has(heroArticle.id)}
                                            bookmarked={bookmarkedIds.has(heroArticle.id)}
                                            disliked={dislikedIds.has(heroArticle.id)}
                                            menuOpen={openMenuId === heroArticle.id}
                                            menuRef={menuRef}
                                            onLike={(e) => toggleLike(heroArticle.id, heroArticle.category ?? activeTab, e)}
                                            onMore={(e) => handleMore(heroArticle.id, e)}
                                            onBookmark={(e) => handleBookmark(heroArticle.id, heroArticle.category ?? activeTab, e)}
                                            onAddToSpace={handleAddToSpace}
                                            onDislike={(e) => handleDislike(heroArticle.id, heroArticle.category ?? activeTab, e)}
                                        />
                                    </div>
                                    {heroArticle.image && (
                                        <div className="discover-hero-image">
                                            <img
                                                src={heroArticle.image}
                                                alt={heroArticle.title}
                                                onError={(e) => {
                                                    (e.target as HTMLImageElement).parentElement!.style.display = "none";
                                                }}
                                            />
                                        </div>
                                    )}
                                </a>
                            )}

                            {/* Grid */}
                            {gridArticles.length > 0 && (
                                <div className="discover-grid">
                                    {gridArticles.map((article, idx) => (
                                        <a
                                            key={article.id}
                                            className="discover-card"
                                            href={`/discover/article/${article.id}`}
                                            style={{ animationDelay: `${Math.min(idx, 11) * 45}ms` }}
                                            onClick={(e) => { e.preventDefault(); openArticle(article); }}
                                        >
                                            <div className="discover-card-image">
                                                {article.image ? (
                                                    <img
                                                        src={article.image}
                                                        alt={article.title}
                                                        loading="lazy"
                                                        onError={(e) => {
                                                            const wrap = (e.target as HTMLImageElement).parentElement!;
                                                            wrap.innerHTML = `<div class="discover-card-image-placeholder"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg></div>`;
                                                        }}
                                                    />
                                                ) : (
                                                    <div className="discover-card-image-placeholder">
                                                        <Newspaper size={24} />
                                                    </div>
                                                )}
                                            </div>
                                            <div className="discover-card-meta">
                                                <span>{timeAgo(article.publishedAt)}</span>
                                            </div>
                                            <h3 className="discover-card-title">{article.title}</h3>
                                            {article.description && (
                                                <p className="discover-card-description">{article.description}</p>
                                            )}
                                            <ArticleFooter
                                                articleId={article.id}
                                                source={article.source}
                                                liked={likedIds.has(article.id)}
                                                bookmarked={bookmarkedIds.has(article.id)}
                                                disliked={dislikedIds.has(article.id)}
                                                menuOpen={openMenuId === article.id}
                                                menuRef={menuRef}
                                                onLike={(e) => toggleLike(article.id, article.category ?? activeTab, e)}
                                                onMore={(e) => handleMore(article.id, e)}
                                                onBookmark={(e) => handleBookmark(article.id, article.category ?? activeTab, e)}
                                                onAddToSpace={handleAddToSpace}
                                                onDislike={(e) => handleDislike(article.id, article.category ?? activeTab, e)}
                                            />
                                        </a>
                                    ))}
                                </div>
                            )}
                        </>
                    )}

                    {/* Infinite scroll sentinel */}
                    <div ref={sentinelRef} style={{ height: 1 }} />

                    {/* Load more spinner */}
                    {loadingMore && (
                        <div className="discover-load-more">
                            <div className="discover-load-more-spinner" />
                        </div>
                    )}

                    {/* End of feed */}
                    {!hasMore && !loadingMore && !loadingArticles && articles.length > 0 && (
                        <div className="discover-feed-end">
                            <div className="discover-feed-end-line" />
                            <span className="discover-feed-end-text">You&apos;re all caught up</span>
                            <div className="discover-feed-end-line" />
                        </div>
                    )}
                </div>

                {/* ── Sidebar ── */}
                <aside className="discover-sidebar">
                    {/* Make it yours */}
                    <div className="discover-widget">
                        <p className="discover-interests-title">Make it yours</p>
                        <p className="discover-interests-subtitle">Select topics and interests to customize your Discover experience</p>
                        <div className="discover-interest-pills">
                            {TOPIC_OPTIONS.map((t) => {
                                const Icon = t.icon;
                                return (
                                    <button
                                        key={t.id}
                                        className={`discover-interest-pill ${selectedInterests.includes(t.id) ? "selected" : ""}`}
                                        onClick={() => toggleInterest(t.id)}
                                    >
                                        <Icon size={13} strokeWidth={1.75} />
                                        {t.label}
                                    </button>
                                );
                            })}
                        </div>
                        <button
                            className={`discover-save-btn ${interestsSaved ? "saved" : ""}`}
                            onClick={handleSaveInterests}
                        >
                            {interestsSaved
                                ? <><Sparkles size={13} />&nbsp;Saved!</>
                                : "Save Interests"
                            }
                        </button>
                    </div>

                    {/* Weather */}
                    {loadingSidebar ? (
                        <div className="discover-widget">
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                                <div className="skeleton" style={{ height: 32, width: "40%", borderRadius: 6 }} />
                                <div className="skeleton" style={{ height: 14, width: "30%", borderRadius: 4 }} />
                            </div>
                            <div className="skeleton" style={{ height: 13, width: "60%", borderRadius: 4, marginBottom: 12 }} />
                            <div className="skeleton" style={{ height: 1, marginBottom: 12 }} />
                            <div style={{ display: "flex", gap: 8 }}>
                                {[1,2,3,4,5].map(i => <div key={i} className="skeleton" style={{ flex: 1, height: 48, borderRadius: 6 }} />)}
                            </div>
                        </div>
                    ) : sidebar?.weather && Object.keys(sidebar.weather).length > 0 ? (
                        <div className={`discover-widget discover-weather-widget discover-weather-${sidebar.weather.icon}`}>
                            {/* Row 1: icon + temp + feels_like (left) | condition (right) */}
                            <div className="discover-weather-row1">
                                <div className="discover-weather-left">
                                    <WeatherIcon code={sidebar.weather.icon} size={22} className="discover-weather-icon-svg" />
                                    <div className="discover-weather-temp-group">
                                        <div className="discover-weather-temp">
                                            {sidebar.weather.temp_c}°
                                            <span className="discover-weather-unit">C</span>
                                        </div>
                                        <div className="discover-weather-feels">
                                            Feels {sidebar.weather.feels_like_c}°
                                        </div>
                                    </div>
                                </div>
                                <span className="discover-weather-desc">{sidebar.weather.description}</span>
                            </div>
                            {/* City + H/L */}
                            <div className="discover-weather-row2">
                                <span className="discover-weather-city">{sidebar.weather.city}</span>
                                {(sidebar.weather.high_c != null || sidebar.weather.forecast?.[0]) && (
                                    <span className="discover-weather-hl">
                                        H: {sidebar.weather.high_c ?? sidebar.weather.forecast?.[0]?.max_c}° L: {sidebar.weather.low_c ?? sidebar.weather.forecast?.[0]?.min_c}°
                                    </span>
                                )}
                            </div>
                            <div className="discover-weather-divider" />
                            {/* 5-day forecast */}
                            {sidebar.weather.forecast?.length > 0 && (
                                <div className="discover-weather-forecast">
                                    {sidebar.weather.forecast.slice(0, 5).map((day, i) => (
                                        <div key={i} className="discover-forecast-day">
                                            <span className="discover-forecast-label">{dayLabel(day.date, i).toUpperCase()}</span>
                                            <WeatherIcon code={day.icon} size={15} className="discover-forecast-icon-svg" />
                                            <span className="discover-forecast-temp">{day.max_c}°</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                            {/* Hover overlay — "Use precise location" like Perplexity */}
                            {!coords && (
                                <div className="discover-weather-overlay">
                                    <button className="discover-location-btn" onClick={requestLocation}>
                                        <MapPin size={13} />
                                        Use precise location
                                    </button>
                                </div>
                            )}
                        </div>
                    ) : (
                        /* Weather unavailable — show compact location card */
                        <div className="discover-widget discover-weather-widget discover-weather-empty">
                            <div className="discover-weather-row1">
                                <div className="discover-weather-left">
                                    <CloudSun size={22} strokeWidth={1.5} className="discover-weather-icon-svg" />
                                    <div className="discover-weather-temp-group">
                                        <div className="discover-weather-temp">--°<span className="discover-weather-unit">C</span></div>
                                        <div className="discover-weather-feels">Weather unavailable</div>
                                    </div>
                                </div>
                            </div>
                            <button className="discover-location-btn" onClick={requestLocation} style={{ marginTop: 10, width: "100%" }}>
                                <MapPin size={13} />
                                Use precise location
                            </button>
                        </div>
                    )}

                    {/* Market Outlook */}
                    {loadingSidebar ? (
                        <div className="discover-widget">
                            <div className="skeleton discover-skeleton-line" style={{ height: 14, width: "50%", marginBottom: 12 }} />
                            <div className="discover-market-grid">
                                {Array.from({ length: 4 }).map((_, i) => (
                                    <div key={i}>
                                        <div className="skeleton discover-skeleton-line" style={{ height: 12, marginBottom: 6 }} />
                                        <div className="skeleton discover-skeleton-line" style={{ height: 20 }} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : sidebar?.market && Object.keys(sidebar.market).length > 0 ? (
                        <div className="discover-widget">
                            <p className="discover-widget-title">Market Outlook</p>
                            <div className="discover-market-grid">
                                {MARKET_ORDER.filter((k) => sidebar.market[k]).map((key) => {
                                    const item = sidebar.market[key];
                                    const isUp = item.change_pct >= 0;
                                    return (
                                        <div key={key} className="discover-market-item">
                                            <span className="discover-market-name">{key}</span>
                                            <span className="discover-market-price">
                                                {formatPrice(item.price, item.is_crypto)}
                                            </span>
                                            <span className={`discover-market-change ${isUp ? "up" : "down"}`}>
                                                {isUp ? "↑" : "↓"}{Math.abs(item.change_pct).toFixed(2)}%
                                            </span>
                                            <Sparkline data={item.sparkline} isUp={isUp} />
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ) : null}

                    {/* Trending Companies */}
                    {loadingSidebar ? (
                        <div className="discover-widget">
                            <div className="skeleton discover-skeleton-line" style={{ height: 14, width: "60%", marginBottom: 12 }} />
                            {Array.from({ length: 5 }).map((_, i) => (
                                <div key={i} style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
                                    <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6, flexShrink: 0 }} />
                                    <div style={{ flex: 1 }}>
                                        <div className="skeleton discover-skeleton-line" style={{ height: 12, marginBottom: 4 }} />
                                        <div className="skeleton discover-skeleton-line" style={{ height: 10, width: "40%" }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : sidebar?.trending_stocks && sidebar.trending_stocks.length > 0 ? (
                        <div className="discover-widget">
                            <p className="discover-widget-title">Trending Companies</p>
                            <div className="discover-trending-list">
                                {sidebar.trending_stocks.map((stock) => {
                                    const isUp = stock.change_pct >= 0;
                                    return (
                                        <a
                                            key={stock.symbol}
                                            className="discover-trending-item"
                                            href={`https://finance.yahoo.com/quote/${stock.symbol}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                        >
                                            <div className="discover-trending-favicon">
                                                <img
                                                    src={stock.favicon}
                                                    alt={stock.name}
                                                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                                />
                                            </div>
                                            <div className="discover-trending-info">
                                                <p className="discover-trending-name">{stock.name}</p>
                                                <p className="discover-trending-ticker">{stock.symbol}</p>
                                            </div>
                                            <div className="discover-trending-price-col">
                                                <p className="discover-trending-price">
                                                    ${stock.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                                </p>
                                                <p className={`discover-trending-change ${isUp ? "up" : "down"}`}>
                                                    {isUp ? "+" : ""}{stock.change_pct.toFixed(2)}%
                                                </p>
                                            </div>
                                        </a>
                                    );
                                })}
                            </div>
                        </div>
                    ) : null}
                </aside>
            </div>
        </div>
    );
}
