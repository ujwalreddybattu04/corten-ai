"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    ArrowLeft, Share2, Send, Newspaper,
    Clock, Bookmark, MoreHorizontal, ChevronDown,
    Link2, Copy, Check, X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
    category?: string;
}

interface SearchSource {
    url: string;
    title: string;
    domain: string;
    favicon?: string;
    faviconUrl?: string;
    snippet?: string;
    citationIndex: number;
}

const API_BASE = typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? ""
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

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

// ── GPT-style animated thinking text driven by REAL backend SSE events ───────

function ArticleThinkingText({ messages }: { messages: string[] }) {
    const [displayIdx, setDisplayIdx] = useState(0);
    const [text, setText] = useState("");
    const charRef = useRef(0);
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const [typing, setTyping] = useState(true);
    const shownCountRef = useRef(0);

    // When a new message arrives from backend, jump to it immediately
    useEffect(() => {
        if (messages.length > 0 && messages.length > shownCountRef.current) {
            shownCountRef.current = messages.length;
            setDisplayIdx(messages.length - 1);
        }
    }, [messages.length]);

    const current = messages[displayIdx] || "Thinking";

    // Typewriter: reveal one char at a time
    useEffect(() => {
        charRef.current = 0;
        setText("");
        setTyping(true);
        intervalRef.current = setInterval(() => {
            charRef.current++;
            if (charRef.current <= current.length) {
                setText(current.slice(0, charRef.current));
            } else {
                setTyping(false);
                if (intervalRef.current) clearInterval(intervalRef.current);
            }
        }, 12);
        return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    }, [displayIdx, current]);

    // If no new message arrives for a while, stay on last message (no cycling to stale ones)

    return (
        <>
            <span className="article-thought-shimmer">{text}</span>
            <span className="article-thought-cursor" />
        </>
    );
}

// ── Corten sparkle icon (like Perplexity's logo in articles) ─────────────────
function CortenSparkle({ size = 16 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="article-sparkle-icon">
            <path d="M12 2L9.5 9.5L2 12L9.5 14.5L12 22L14.5 14.5L22 12L14.5 9.5L12 2Z" fill="currentColor" />
        </svg>
    );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ArticleDetailPage() {
    const params = useParams();
    const router = useRouter();
    const id = params.id as string;

    const [article, setArticle] = useState<Article | null>(null);
    const [related, setRelated] = useState<Article[]>([]);
    const [followUp, setFollowUp] = useState("");
    const [copied, setCopied] = useState(false);
    const [sourcesPanelOpen, setSourcesPanelOpen] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    // AI-generated content state
    const [aiContent, setAiContent] = useState("");
    const [aiSources, setAiSources] = useState<SearchSource[]>([]);
    const [isGenerating, setIsGenerating] = useState(false);
    const [thoughtSteps, setThoughtSteps] = useState(0);
    const [liveSteps, setLiveSteps] = useState<string[]>([]);
    const [showThought, setShowThought] = useState(false);
    const abortRef = useRef<AbortController | null>(null);

    // Streaming buffer for smooth text rendering
    const streamBufferRef = useRef("");
    const animFrameRef = useRef<number | null>(null);

    useEffect(() => {
        let cancelled = false;

        try {
            const stored = sessionStorage.getItem(`discover_article_${id}`);
            if (stored) {
                const a = JSON.parse(stored) as Article;
                setArticle(a);
                fetchRelated(a.category ?? "technology", a.id);
                // Small delay to avoid React 18 strict-mode double-mount abort
                const timer = setTimeout(() => {
                    if (!cancelled) generateAISummary(a.title, a.description, a.url);
                }, 50);
                return () => {
                    cancelled = true;
                    clearTimeout(timer);
                    if (abortRef.current) abortRef.current.abort();
                    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
                };
            } else {
                router.replace("/discover");
            }
        } catch {
            router.replace("/discover");
        }

        return () => {
            cancelled = true;
            if (abortRef.current) abortRef.current.abort();
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        };
    }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

    // ── AI Summary Generation ────────────────────────────────────────────────

    const generateAISummary = useCallback(async (title: string, description?: string, articleUrl?: string) => {
        setIsGenerating(true);
        setAiContent("");
        setAiSources([]);
        setThoughtSteps(0);
        setLiveSteps([]);
        streamBufferRef.current = "";

        const controller = new AbortController();
        abortRef.current = controller;

        // Smooth text drip loop
        const drainBuffer = () => {
            if (streamBufferRef.current.length > 0) {
                const sliceEnd = Math.min(15, streamBufferRef.current.length);
                const nextSpace = streamBufferRef.current.indexOf(" ", 10);
                const end = (nextSpace !== -1 && nextSpace < 25) ? nextSpace + 1 : sliceEnd;
                const slice = streamBufferRef.current.slice(0, end);
                streamBufferRef.current = streamBufferRef.current.slice(end);
                setAiContent(prev => prev + slice);
            }
            animFrameRef.current = requestAnimationFrame(drainBuffer);
        };
        animFrameRef.current = requestAnimationFrame(drainBuffer);

        try {
            const response = await fetch(`${API_BASE}/api/v1/discover/article/summarize`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title,
                    url: articleUrl || "",
                    description: description || "",
                }),
                signal: controller.signal,
            });

            if (!response.ok || !response.body) {
                setIsGenerating(false);
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    const payload = line.slice(6).trim();
                    if (payload === "[DONE]") continue;

                    try {
                        const evt = JSON.parse(payload);
                        if (evt.type === "sources" && (evt.sources || evt.items)) {
                            setAiSources(evt.sources || evt.items || []);
                        } else if (evt.type === "token") {
                            const tokenText = evt.content ?? evt.data ?? "";
                            if (tokenText) {
                                streamBufferRef.current += tokenText;
                            }
                        } else if (evt.type === "query_step" || evt.type === "thought" || evt.type === "status") {
                            setThoughtSteps(prev => prev + 1);
                            const stepContent = evt.content ?? evt.data ?? "";
                            if (stepContent) {
                                setLiveSteps(prev => [...prev, stepContent]);
                            }
                        }
                    } catch { /* skip */ }
                }
            }
        } catch (e: unknown) {
            if (e instanceof Error && e.name !== "AbortError") {
                console.error("AI summary failed:", e);
            }
        } finally {
            setTimeout(() => {
                if (streamBufferRef.current.length > 0) {
                    setAiContent(prev => prev + streamBufferRef.current);
                    streamBufferRef.current = "";
                }
                if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
                setIsGenerating(false);
            }, 500);
        }
    }, []);

    // ── Fetch related ────────────────────────────────────────────────────────

    const fetchRelated = async (category: string, excludeId: string) => {
        try {
            const res = await fetch(`${API_BASE}/api/v1/discover?category=${category}&page=1&page_size=8`);
            if (!res.ok) return;
            const data = await res.json();
            setRelated(
                (data.articles ?? [])
                    .filter((a: Article) => a.id !== excludeId)
                    .map((a: Article) => ({ ...a, category }))
                    .slice(0, 4)
            );
        } catch { /* ignore */ }
    };

    const navigateToRelated = (ra: Article) => {
        if (abortRef.current) abortRef.current.abort();
        if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        try { sessionStorage.setItem(`discover_article_${ra.id}`, JSON.stringify(ra)); } catch { /* */ }
        router.push(`/discover/article/${ra.id}`);
    };

    const handleFollowUp = (e: React.FormEvent) => {
        e.preventDefault();
        const q = followUp.trim();
        if (!q || !article) return;

        // Build a context-aware query so the search page LLM knows which article
        const contextQuery = `Regarding the article "${article.title}": ${q}`;

        const sp = new URLSearchParams({
            q: contextQuery,
            fromArticle: article.title,
            fromArticleImg: article.image ?? "",
        });
        router.push(`/search?${sp.toString()}`);
    };

    const handleShare = () => {
        if (!article) return;
        if (navigator.share) {
            navigator.share({ title: article.title, url: article.url });
        } else {
            navigator.clipboard.writeText(article.url);
        }
    };

    const handleCopyLink = () => {
        if (!article) return;
        navigator.clipboard.writeText(article.url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    // All sources for display: AI sources + original article source
    const allSources = aiSources.length > 0
        ? aiSources
        : article
            ? [{ url: article.url, title: article.title, domain: article.source.domain, favicon: article.source.favicon, snippet: article.description, citationIndex: 1 }]
            : [];

    // ── Loading state ──────────────────────────────────────────────────────────
    if (!article) {
        return (
            <div className="article-page">
                <div className="article-loading">
                    <div className="article-loading-spinner" />
                </div>
            </div>
        );
    }

    return (
        <div className={`article-page ${sourcesPanelOpen ? "article-page--panel-open" : ""}`}>
            {/* ── Grid layout (main + sources panel) ── */}
            <div className="article-layout">
              <div className="article-main">
                {/* ── Top bar (inside main so it shifts with content) ── */}
                <div className="article-topbar">
                    <button className="article-back-btn" onClick={() => router.push("/discover")}>
                        <ArrowLeft size={14} />
                        Back to Discover
                    </button>
                    <div className="article-topbar-actions">
                        <button className="article-topbar-icon-btn" title="More options">
                            <MoreHorizontal size={16} />
                        </button>
                        <button className="article-topbar-icon-btn" title="Bookmark">
                            <Bookmark size={16} />
                        </button>
                        <button className="article-topbar-share" onClick={handleShare}>
                            <Share2 size={13} />
                            Share
                        </button>
                    </div>
                </div>
                {/* ── Scrollable body ── */}
                <div className="article-body">
                  <div className="article-inner">

                    {/* ── Title ── */}
                    <h1 className="article-h1">{article.title}</h1>

                    {/* ── Lead paragraph (article description) ── */}
                    {article.description && (
                        <p className="article-lead">
                            {article.description}
                            {/* Inline source badge after text */}
                            <span className="article-inline-citation">
                                <span className="article-citation-text">{article.source.domain}</span>
                                {aiSources.length > 0 && (
                                    <span className="article-citation-extra">+{aiSources.length}</span>
                                )}
                            </span>
                        </p>
                    )}

                    {/* ── Sparkle + Published row (like Perplexity) ── */}
                    <div className="article-meta-row">
                        <CortenSparkle size={16} />
                        <div className="article-published-row">
                            <Clock size={13} />
                            <span>Published {timeAgo(article.publishedAt)}</span>
                        </div>
                    </div>

                    {/* ── Source cards (ALWAYS visible — Perplexity style) ── */}
                    <div className="article-source-cards">
                        {allSources.slice(0, 4).map((src, i) => (
                            <a
                                key={i}
                                href={src.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="article-source-card"
                            >
                                <img
                                    className="article-source-card-favicon"
                                    src={src.favicon || src.faviconUrl || `https://www.google.com/s2/favicons?domain=${src.domain}&sz=32`}
                                    alt=""
                                    width={16}
                                    height={16}
                                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                />
                                <span className="article-source-card-domain">{src.domain}</span>
                                <p className="article-source-card-title">{src.title}</p>
                            </a>
                        ))}
                    </div>

                    {/* ── Hero image ── */}
                    {article.image && (
                        <div className="article-hero-img">
                            <img
                                src={article.image}
                                alt={article.title}
                                onError={(e) => { (e.target as HTMLImageElement).parentElement!.style.display = "none"; }}
                            />
                        </div>
                    )}

                    {/* ── AI Generated Summary ── */}
                    {(aiContent || isGenerating) && (
                        <div className="article-ai-section">
                            {/* GPT-style animated thinking indicator */}
                            {(thoughtSteps > 0 || isGenerating) && (
                                <button
                                    className="article-thought-toggle"
                                    onClick={() => setShowThought(!showThought)}
                                >
                                    <span className={`article-thought-dot ${!isGenerating ? 'done' : ''}`} />
                                    {isGenerating && !aiContent ? (
                                        <ArticleThinkingText messages={liveSteps} />
                                    ) : isGenerating && aiContent ? (
                                        <span className="article-thought-shimmer">Synthesizing the summary</span>
                                    ) : (
                                        <span>Thought for {thoughtSteps} step{thoughtSteps !== 1 ? "s" : ""}</span>
                                    )}
                                    <ChevronDown
                                        size={13}
                                        style={{
                                            transform: showThought ? "rotate(180deg)" : "none",
                                            transition: "transform 0.2s",
                                        }}
                                    />
                                </button>
                            )}

                            {/* Streaming content */}
                            <div className="article-ai-content">
                                {aiContent ? (
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            h1: ({ children }) => <h2 className="article-ai-h2">{children}</h2>,
                                            h2: ({ children }) => <h2 className="article-ai-h2">{children}</h2>,
                                            h3: ({ children }) => <h3 className="article-ai-h3">{children}</h3>,
                                            p: ({ children }) => <p className="article-ai-p">{children}</p>,
                                            ul: ({ children }) => <ul className="article-ai-ul">{children}</ul>,
                                            ol: ({ children }) => <ol className="article-ai-ol">{children}</ol>,
                                            li: ({ children }) => <li className="article-ai-li">{children}</li>,
                                            strong: ({ children }) => <strong className="article-ai-strong">{children}</strong>,
                                            blockquote: ({ children }) => <blockquote className="article-ai-blockquote">{children}</blockquote>,
                                        }}
                                    >
                                        {aiContent}
                                    </ReactMarkdown>
                                ) : (
                                    <div className="article-ai-loading">
                                        <div className="article-ai-loading-bar" />
                                        <div className="article-ai-loading-bar short" />
                                        <div className="article-ai-loading-bar shorter" />
                                    </div>
                                )}
                                {isGenerating && aiContent && <span className="article-ai-cursor" />}
                            </div>
                        </div>
                    )}

                    {/* ── Sources summary bar (clickable to open panel) ── */}
                    {!isGenerating && (
                        <div className="article-sources-summary">
                            <button
                                className="article-sources-left"
                                onClick={() => setSourcesPanelOpen(true)}
                            >
                                <div className="article-sources-favicons">
                                    {allSources.slice(0, 3).map((src, i) => (
                                        <img
                                            key={i}
                                            className="article-sources-favicon"
                                            src={src.favicon || src.faviconUrl || `https://www.google.com/s2/favicons?domain=${src.domain}&sz=32`}
                                            alt=""
                                            width={16}
                                            height={16}
                                            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                        />
                                    ))}
                                </div>
                                <span className="article-sources-count">{allSources.length} source{allSources.length !== 1 ? "s" : ""}</span>
                            </button>
                            <div className="article-sources-actions">
                                <a
                                    href={article.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="article-sources-action-btn"
                                    title="Open original"
                                >
                                    <Link2 size={15} />
                                </a>
                                <button
                                    className="article-sources-action-btn"
                                    title="Copy link"
                                    onClick={handleCopyLink}
                                >
                                    {copied ? <Check size={15} /> : <Copy size={15} />}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* ── Discover more ── */}
                    {related.length > 0 && (
                        <div className="article-related">
                            <h3 className="article-related-heading">
                                <CortenSparkle size={16} />
                                Discover more
                            </h3>
                            <div className="article-related-grid">
                                {related.map((ra) => (
                                    <button
                                        key={ra.id}
                                        className="article-related-card"
                                        onClick={() => navigateToRelated(ra)}
                                    >
                                        <div className="article-related-img">
                                            {ra.image ? (
                                                <img
                                                    src={ra.image}
                                                    alt={ra.title}
                                                    onError={(e) => {
                                                        const wrap = (e.target as HTMLImageElement).parentElement!;
                                                        wrap.classList.add("article-related-img-fallback");
                                                        (e.target as HTMLImageElement).style.display = "none";
                                                    }}
                                                />
                                            ) : (
                                                <div className="article-related-img-placeholder">
                                                    <Newspaper size={18} />
                                                </div>
                                            )}
                                        </div>
                                        <p className="article-related-title">{ra.title}</p>
                                        {ra.description && (
                                            <p className="article-related-desc">{ra.description}</p>
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    <div style={{ height: 80 }} />
                  </div>
                </div>

                {/* ── Fixed follow-up bar ── */}
                <div className="article-followup-bar">
                    <form className="article-followup-form" onSubmit={handleFollowUp}>
                        <input
                            ref={inputRef}
                            className="article-followup-input"
                            value={followUp}
                            onChange={(e) => setFollowUp(e.target.value)}
                            placeholder="Ask follow-up"
                            autoComplete="off"
                        />
                        <button
                            type="submit"
                            className={`article-followup-send ${followUp.trim() ? "active" : ""}`}
                            disabled={!followUp.trim()}
                        >
                            <Send size={14} />
                        </button>
                    </form>
                </div>
              </div>

              {/* ── Sources Panel (grid column, like search page) ── */}
              <aside className="article-sources-panel">
                  <div className="article-sources-panel-header">
                      <h3 className="article-sources-panel-title">
                          {allSources.length} source{allSources.length !== 1 ? "s" : ""}
                      </h3>
                      <button
                          className="article-sources-panel-close"
                          onClick={() => setSourcesPanelOpen(false)}
                          aria-label="Close sources panel"
                      >
                          <X size={16} />
                      </button>
                  </div>
                  <div className="article-sources-panel-list">
                      {allSources.map((src, i) => {
                          const rawDomain = src.domain || (() => { try { return new URL(src.url).hostname; } catch { return ""; } })();
                          const displayDomain = rawDomain.replace(/^www\./, "");
                          return (
                              <a
                                  key={i}
                                  href={src.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="article-sources-panel-item"
                              >
                                  <div className="article-sources-panel-item-top">
                                      <div className="article-sources-panel-item-icon">
                                          <img
                                              src={src.favicon || src.faviconUrl || `https://www.google.com/s2/favicons?domain=${displayDomain}&sz=32`}
                                              alt=""
                                              width={16}
                                              height={16}
                                              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                          />
                                      </div>
                                      <span className="article-sources-panel-item-domain">{displayDomain}</span>
                                  </div>
                                  <div className="article-sources-panel-item-title">{src.title}</div>
                                  {src.snippet && (
                                      <div className="article-sources-panel-item-snippet">{src.snippet}</div>
                                  )}
                              </a>
                          );
                      })}
                  </div>
              </aside>
            </div>
        </div>
    );
}
