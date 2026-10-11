"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useState, useCallback, useEffect } from "react";
import { motion } from "framer-motion";
import { useSearch } from "@/hooks/useSearch";
import AnswerStream from "@/components/thread/AnswerStream";
import AnswerSkeleton from "@/components/thread/AnswerSkeleton";
import ImagesGrid from "@/components/thread/ImagesGrid";
import { Sparkles, Globe, Image as ImageIcon, Pencil, Copy, Check, CornerDownRight } from "lucide-react";
import { Favicon } from "@/components/common";
import ThreadMenu from "@/components/thread/ThreadMenu";
import ShareModal from "@/components/thread/ShareModal";

function cleanSnippet(text: string): string {
    const cleaned = text
        .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')                              // images → space
        .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1 ')                           // [text](url) → text
        .replace(/\[[^\]]*\]/g, ' ')                                        // orphan brackets
        .replace(/https?:\/\/\S+/g, ' ')                                    // bare URLs (space to prevent word-joining)
        .replace(/#{1,6}\s*/g, '')                                          // headings
        .replace(/\*{2}([^*\n]+)\*{2}/g, '$1')                             // **bold**
        .replace(/\*([^*\n]+)\*/g, '$1')                                    // *italic*
        .replace(/\*+/g, ' ')                                               // leftover asterisks
        .replace(/`[^`]+`/g, '')                                            // inline code
        // Navigation / boilerplate patterns
        .replace(/Skip to (main )?content\.?/gi, '')
        .replace(/\bISSN[:\s]+[\d\-X]+/gi, '')                             // ISSN numbers
        .replace(/\bVol\.\s*\d+.*?(?=\.|$)/gi, '')                        // Vol. 11, Issue: 5...
        .replace(/(\s*\.\s*){3,}/g, '. ')                                   // ". . . ." → ". "
        .replace(/(\s+[A-Z][a-z]*\.?\s*){5,}/g, ' ')                      // nav word lists
        .replace(/\|/g, ' ')
        .replace(/\n+/g, ' ')
        .replace(/\s{2,}/g, ' ')
        .replace(/^[\s.,]+/, '')                                            // leading junk
        .trim();

    // If the snippet still looks like navigation junk (many short words), return empty
    const wordList = cleaned.split(' ');
    const shortWordRatio = wordList.filter(w => w.length <= 3).length / (wordList.length || 1);
    if (shortWordRatio > 0.6 && wordList.length > 5) return '';

    if (cleaned.length <= 220) return cleaned;
    return cleaned.slice(0, 220).replace(/\s+\S*$/, '') + '…';
}

function cleanTitle(text: string): string {
    return text
        .replace(/^\[PDF\]\s*/i, '')        // [PDF] prefix
        .replace(/\s*\|\s*$/, '')           // trailing pipe
        .trim();
}

function SearchPageContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const query = searchParams.get("q") || "";
    const focusMode = searchParams.get("focus") || "all";
    const threadId = searchParams.get("id") || undefined;
    const fromArticle = searchParams.get("fromArticle") || "";
    const fromArticleImg = searchParams.get("fromArticleImg") || "";
    const [followUp, setFollowUp] = useState("");
    const [activeTab, setActiveTab] = useState<"answer" | "links" | "images">("answer");
    const [sourcesPanelOpen, setSourcesPanelOpen] = useState(false);
    const [activePanelSources, setActivePanelSources] = useState<any[]>([]);
    const [activePanelQuery, setActivePanelQuery] = useState("");
    const [copied, setCopied] = useState(false);
    const [copiedQueryId, setCopiedQueryId] = useState<string | null>(null);
    const [shareOpen, setShareOpen] = useState(false);
    const [editingQueryId, setEditingQueryId] = useState<string | null>(null);
    const [editingQueryText, setEditingQueryText] = useState("");

    const {
        threadId: activeThreadId,
        history,
        query: currentQuery,
        answer,
        displayAnswer,
        sources,
        images,
        researchSteps,
        relatedQuestions,
        isStreaming,
        isConnecting,
        isDisplayComplete,
        error,
        model,
        thoughtTime,
        appendQuery
    } = useSearch(query, focusMode, threadId);

    // --- EFFECT: When global sources update, update the active panel IF it was for the current query ---
    useEffect(() => {
        if (sources.length > 0 && !isStreaming) {
            // If the panel is open and showing the current query (or just opened), update it
            if (activePanelQuery === "" || activePanelQuery === currentQuery) {
                setActivePanelSources(sources);
                setActivePanelQuery(currentQuery);
            }
        }
    }, [sources, isStreaming, currentQuery, activePanelQuery]);

    const toggleSourcesPanel = (open: boolean, msgSources?: any[], msgQuery?: string) => {
        if (open) {
            if (msgSources && msgQuery) {
                setActivePanelSources(msgSources);
                setActivePanelQuery(msgQuery);
            } else {
                // Fallback to latest
                setActivePanelSources(sources);
                setActivePanelQuery(currentQuery);
            }
            setSourcesPanelOpen(true);
        } else {
            setSourcesPanelOpen(false);
        }
    };

    const handleFollowUp = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        const queryText = followUp.trim();
        if (!queryText || isConnecting || isStreaming) return;
        setFollowUp("");
        appendQuery(queryText);
    }, [followUp, appendQuery, isConnecting, isStreaming]);

    const handleRelatedSelect = useCallback((q: string) => {
        appendQuery(q);
    }, [appendQuery]);

    const handleCopyQuery = useCallback((queryText: string, queryId: string) => {
        navigator.clipboard.writeText(queryText);
        setCopiedQueryId(queryId);
        setTimeout(() => setCopiedQueryId(null), 2000);
    }, []);

    const handleStartEdit = useCallback((queryText: string, queryId: string) => {
        setEditingQueryId(queryId);
        setEditingQueryText(queryText);
    }, []);

    const handleCancelEdit = useCallback(() => {
        setEditingQueryId(null);
        setEditingQueryText("");
    }, []);

    const handleSubmitEdit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        const newText = editingQueryText.trim();
        if (!newText) return;
        setEditingQueryId(null);
        setEditingQueryText("");
        // Navigate to a fresh search with the edited query — this REPLACES the current answer
        router.push(`/search?q=${encodeURIComponent(newText)}`);
    }, [editingQueryText, router]);



    const handleCopy = useCallback(() => {
        navigator.clipboard.writeText(answer);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, [answer]);

    const isLoading = isConnecting && !answer && !error;
    const hasSources = sources.length > 0;

    // Scroll to the new query when it becomes active
    useEffect(() => {
        if (currentQuery && (isConnecting || isStreaming)) {
            const queryRow = document.getElementById("current-query-row");
            const scrollable = document.querySelector(".sp-content");
            if (queryRow && scrollable) {
                // Wait slightly for the motion.div to mount and begin expanding
                setTimeout(() => {
                    if (history.length > 0) {
                        // For follow-ups: perfectly frame the new query at the top of the view
                        queryRow.scrollIntoView({ behavior: "smooth", block: "start" });
                    } else {
                        // For the first query: just ensure we're at the bottom so the initial animations look clean
                        scrollable.scrollTo({ top: scrollable.scrollHeight, behavior: "smooth" });
                    }
                }, 50);
            }
        }
    }, [currentQuery, isConnecting, isStreaming, history.length]);

    return (
        <>
        <div className="sp-page">
            <div className={`sp-layout ${sourcesPanelOpen ? "sp-layout--panel-open" : ""}`}>
                {/* ─── Main Column ─── */}
                <div className="sp-main">
                    {/* Responsive Tab Bar & Mobile Header */}
                    <div className="sp-header-container">
                        <motion.div
                            className="sp-tabbar"
                            initial={{ opacity: 0, y: -10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5 }}
                        >
                            <div className="sp-tabs">
                                <button
                                    className={`sp-tab ${activeTab === "answer" ? "active" : ""}`}
                                    onClick={() => setActiveTab("answer")}
                                    suppressHydrationWarning
                                >
                                    <Sparkles size={14} />
                                    <span>Answer</span>
                                </button>
                                <button
                                    className={`sp-tab ${activeTab === "links" ? "active" : ""}`}
                                    onClick={() => setActiveTab("links")}
                                    suppressHydrationWarning
                                >
                                    <Globe size={14} />
                                    <span>Links</span>
                                </button>
                                <button
                                    className={`sp-tab ${activeTab === "images" ? "active" : ""}`}
                                    onClick={() => setActiveTab("images")}
                                    suppressHydrationWarning
                                >
                                    <ImageIcon size={14} />
                                    <span>Images</span>
                                </button>
                            </div>

                            <div className="sp-tabbar-right">
                                <ThreadMenu
                                    threadId={activeThreadId}
                                    query={currentQuery}
                                    answer={answer}
                                    history={history}
                                    onDelete={() => router.push("/")}
                                    onRename={() => {}}
                                />
                                <button
                                    className="sp-share-btn"
                                    onClick={() => setShareOpen(true)}
                                >
                                    Share
                                </button>
                            </div>
                        </motion.div>
                    </div>

                    {/* Scrollable Content Area */}
                    <div className="sp-content">
                        <div className="sp-content-inner">
                            {/* === ANSWER TAB === */}
                            {activeTab === "answer" && (
                                <div className="sp-thread-container">
                                    {/* Follow-up context card (from Discover article) */}
                                    {fromArticle && (
                                        <div className="sp-from-article-card">
                                            <CornerDownRight size={13} className="sp-from-article-icon" />
                                            <span className="sp-from-article-label">Follow up to</span>
                                            {fromArticleImg && (
                                                <img
                                                    src={fromArticleImg}
                                                    alt=""
                                                    className="sp-from-article-img"
                                                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                                                />
                                            )}
                                            <span className="sp-from-article-title">{fromArticle}</span>
                                        </div>
                                    )}
                                    {/* 1. History Turns */}
                                    {history && history.map((turn, idx) => (
                                        <motion.div
                                            key={`history-${idx}`}
                                            className="sp-thread-turn"
                                            initial={{ opacity: 0, y: 20 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: idx * 0.05 }}
                                        >
                                            <div className="sp-query-row">
                                                <div className="sp-query-bubble-wrap">
                                                    {editingQueryId === `history-${idx}` ? (
                                                        <div className="sp-query-edit-container">
                                                            <textarea
                                                                autoFocus
                                                                className="sp-query-edit-textarea"
                                                                value={editingQueryText}
                                                                onChange={(e) => setEditingQueryText(e.target.value)}
                                                                onKeyDown={(e) => {
                                                                    if (e.key === 'Escape') handleCancelEdit();
                                                                    if (e.key === 'Enter' && !e.shiftKey) {
                                                                        e.preventDefault();
                                                                        handleSubmitEdit(e);
                                                                    }
                                                                }}
                                                                rows={2}
                                                            />
                                                            <div className="sp-query-edit-actions">
                                                                <button type="button" className="sp-query-edit-cancel" onClick={handleCancelEdit}>Cancel</button>
                                                                <button type="button" className="sp-query-edit-save" onClick={handleSubmitEdit}>Save</button>
                                                            </div>
                                                        </div>
                                                    ) : (
                                                        <>
                                                            <div className="sp-query-bubble">{turn.query}</div>
                                                            <div className="sp-query-actions">
                                                                <button
                                                                    className="sp-query-action-btn"
                                                                    onClick={() => handleStartEdit(turn.query, `history-${idx}`)}
                                                                    title="Edit"
                                                                >
                                                                    <Pencil size={13} strokeWidth={2} />
                                                                </button>
                                                                <button
                                                                    className={`sp-query-action-btn ${copiedQueryId === `history-${idx}` ? 'copied' : ''}`}
                                                                    onClick={() => handleCopyQuery(turn.query, `history-${idx}`)}
                                                                    title="Copy"
                                                                >
                                                                    {copiedQueryId === `history-${idx}` ? <Check size={13} strokeWidth={2.5} /> : <Copy size={13} strokeWidth={2} />}
                                                                </button>
                                                            </div>
                                                        </>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="sp-answer-body">
                                                <AnswerStream
                                                    query={turn.query}
                                                    content={turn.answer}
                                                    isStreaming={false}
                                                    sources={turn.sources}
                                                    researchSteps={turn.researchSteps}
                                                    thoughtTime={turn.thoughtTime}
                                                    onCopy={() => {
                                                        setCopied(true);
                                                        setTimeout(() => setCopied(false), 2000);
                                                    }}
                                                    sourcesPanelOpen={sourcesPanelOpen && activePanelQuery === turn.query}
                                                    setSourcesPanelOpen={(o) => toggleSourcesPanel(o, turn.sources, turn.query)}
                                                />
                                            </div>
                                        </motion.div>
                                    ))}

                                    {/* 2. Current Turn (Active) */}
                                    <motion.div
                                        key="current-turn"
                                        className="sp-thread-turn"
                                        initial={{ opacity: 0, y: 20 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                                    >
                                        <div className="sp-query-row" id="current-query-row">
                                            <div className="sp-query-bubble-wrap">
                                                {editingQueryId === 'current' ? (
                                                    <div className="sp-query-edit-container">
                                                        <textarea
                                                            autoFocus
                                                            className="sp-query-edit-textarea"
                                                            value={editingQueryText}
                                                            onChange={(e) => setEditingQueryText(e.target.value)}
                                                            onKeyDown={(e) => {
                                                                if (e.key === 'Escape') handleCancelEdit();
                                                                if (e.key === 'Enter' && !e.shiftKey) {
                                                                    e.preventDefault();
                                                                    handleSubmitEdit(e);
                                                                }
                                                            }}
                                                            rows={2}
                                                        />
                                                        <div className="sp-query-edit-actions">
                                                            <button type="button" className="sp-query-edit-cancel" onClick={handleCancelEdit}>Cancel</button>
                                                            <button type="button" className="sp-query-edit-save" onClick={handleSubmitEdit}>Save</button>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <>
                                                        <div className="sp-query-bubble">{currentQuery}</div>
                                                        <div className="sp-query-actions">
                                                            <button
                                                                className="sp-query-action-btn"
                                                                onClick={() => handleStartEdit(currentQuery, 'current')}
                                                                title="Edit"
                                                            >
                                                                <Pencil size={13} strokeWidth={2} />
                                                            </button>
                                                            <button
                                                                className={`sp-query-action-btn ${copiedQueryId === 'current' ? 'copied' : ''}`}
                                                                onClick={() => handleCopyQuery(currentQuery, 'current')}
                                                                title="Copy"
                                                            >
                                                                {copiedQueryId === 'current' ? <Check size={13} strokeWidth={2.5} /> : <Copy size={13} strokeWidth={2} />}
                                                            </button>
                                                        </div>
                                                    </>
                                                )}
                                            </div>
                                        </div>

                                        {(displayAnswer || isStreaming) && (
                                            <div className="sp-answer-body">
                                                <AnswerStream
                                                    query={currentQuery}
                                                    content={displayAnswer}
                                                    isStreaming={!isDisplayComplete}
                                                    sources={sources}
                                                    researchSteps={researchSteps}
                                                    thoughtTime={thoughtTime}
                                                    onCopy={handleCopy}
                                                    sourcesPanelOpen={sourcesPanelOpen && activePanelQuery === currentQuery}
                                                    setSourcesPanelOpen={(o) => toggleSourcesPanel(o, sources, currentQuery)}
                                                    relatedQuestions={relatedQuestions}
                                                    onRelatedSelect={handleRelatedSelect}
                                                />
                                                {isDisplayComplete && images.length > 0 && (
                                                    <ImagesGrid images={images} mode="strip" />
                                                )}
                                            </div>
                                        )}

                                        {error && !isLoading && (
                                            <div className="sp-error">
                                                <div className="sp-error-icon">⚡</div>
                                                <h2 className="sp-error-title">{error.includes("fetch") ? "Backend not connected" : "Search Error"}</h2>
                                                <p className="sp-error-msg">{error}</p>
                                            </div>
                                        )}
                                    </motion.div>
                                </div>
                            )}

                            {/* === LINKS TAB === */}
                            {activeTab === "links" && (
                                <div className="sp-links-tab">
                                    {sources.length === 0 ? (
                                        <div className="sp-empty-tab">
                                            {isLoading ? (
                                                <div className="sp-links-loading">
                                                    <div className="sp-links-loading-dot" />
                                                    <span>Searching the web...</span>
                                                </div>
                                            ) : error ? (
                                                <div className="sp-links-error">
                                                    <div className="sp-error-icon">⚠️</div>
                                                    <span>{error.includes("Tavily") ? "Web search limit" : error}</span>
                                                </div>
                                            ) : (
                                                "No links found."
                                            )}
                                        </div>
                                    ) : (
                                        <div className="sp-links-list">
                                            {sources.map((src, i) => {
                                                const ld = (src.domain || '').replace(/^www\./, '') || (src.url ? (() => { try { return new URL(src.url).hostname.replace(/^www\./, ''); } catch { return ''; } })() : '');
                                                return (
                                                <a key={i} href={src.url} target="_blank" rel="noopener noreferrer" className="sp-link-item">
                                                    <div className="sp-link-left">
                                                        <div className="sp-link-favicon">
                                                            <Favicon url={src.url} domain={ld} size={20} />
                                                        </div>
                                                        <div className="sp-link-content">
                                                            <div className="sp-link-meta">{ld}</div>
                                                            <div className="sp-link-title">{cleanTitle(src.title || '')}</div>
                                                            {src.snippet && <div className="sp-link-snippet">{cleanSnippet(src.snippet)}</div>}
                                                        </div>
                                                    </div>
                                                </a>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* === IMAGES TAB === */}
                            {activeTab === "images" && (
                                <div className="sp-images-tab">
                                    {images.length > 0 ? (
                                        <ImagesGrid images={images} mode="grid" />
                                    ) : (
                                        <div className="sp-images-loading">
                                            {isConnecting || isStreaming ? "Searching for images..." : "No images found."}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Sticky Input Bar */}
                    {activeTab === "answer" && (
                        <div className="sp-input-bar">
                            <form className="sp-input-form" onSubmit={handleFollowUp}>
                                <button type="button" className="sp-input-attach"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg></button>
                                <input type="text" className="sp-input-field" placeholder="Ask a follow-up" value={followUp} onChange={e => setFollowUp(e.target.value)} />
                                <div className="sp-input-actions">
                                    <button type="button" className="sp-model-btn">Model ▾</button>
                                    <button type="submit" className="sp-submit-btn" disabled={!followUp.trim() || isConnecting || isStreaming}><svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21 23 12 2.01 3 2 10l15 2-15 2z" /></svg></button>
                                </div>
                            </form>
                        </div>
                    )}
                </div>

                {/* Sources Panel — Perplexity-class design */}
                <aside className="sp-sources-panel">
                    <div className="sp-sources-panel-header">
                        <div className="sp-sources-panel-header-left">
                            <h3 className="sp-sources-panel-title">
                                {activePanelSources.length > 0
                                    ? `${activePanelSources.length} sources`
                                    : "Sources"}
                            </h3>

                        </div>
                        <button
                            className="sp-sources-panel-close"
                            onClick={() => setSourcesPanelOpen(false)}
                            aria-label="Close sources panel"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="6" y1="6" y2="18" /><line x1="6" x2="18" y1="6" y2="18" /></svg>
                        </button>
                    </div>
                    {activePanelSources.length > 0 ? (
                        <div className="sp-sources-panel-list">
                            {activePanelSources.map((src, i) => {
                                const rawDomain = src.domain || (src.url ? (() => { try { return new URL(src.url).hostname; } catch { return ''; } })() : '');
                                const displayDomain = rawDomain.replace(/^www\./, '');
                                return (
                                <a
                                    key={i}
                                    href={src.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="sp-source-item"
                                >
                                    <div className="sp-source-item-top">
                                        <div className="sp-source-item-icon">
                                            <Favicon url={src.url} domain={displayDomain} size={16} />
                                        </div>
                                        <div className="sp-source-item-domain">{displayDomain}</div>
                                    </div>
                                    <div className="sp-source-item-title">{cleanTitle(src.title || '')}</div>
                                    {src.snippet && cleanSnippet(src.snippet) && (
                                        <div className="sp-source-item-snippet">{cleanSnippet(src.snippet)}</div>
                                    )}
                                </a>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="sp-sources-empty">
                            <div className="sp-sources-empty-dots">
                                <span></span><span></span><span></span>
                            </div>
                            Finding top sources...
                        </div>
                    )}
                </aside>
            </div >
        </div >

        {/* Share Modal */}
        <ShareModal
            isOpen={shareOpen}
            onClose={() => setShareOpen(false)}
            query={currentQuery ?? ""}
            answer={answer}
        />

</>
    );
}

function SearchPageSkeleton() {
    return (
        <div className="sp-page">
            <div className="sp-layout sp-layout--panel-open">
                <div className="sp-main">
                    <div className="sp-tabbar">
                        <div className="sp-tabs">
                            <button className="sp-tab sp-tab--active" disabled suppressHydrationWarning>
                                <Sparkles size={13} strokeWidth={2.5} />
                                Answer
                            </button>
                            <button className="sp-tab" disabled suppressHydrationWarning>
                                <Globe size={13} strokeWidth={2.5} />
                                Links
                            </button>
                            <button className="sp-tab" disabled suppressHydrationWarning>
                                <ImageIcon size={13} strokeWidth={2.5} />
                                Images
                            </button>
                        </div>
                    </div>
                    <div className="sp-content">
                        <div className="sp-query-row" style={{ opacity: 0 }}>
                            <div className="sp-query-bubble">Loading...</div>
                        </div>
                        <AnswerSkeleton />
                    </div>
                    <div className="sp-input-bar">
                        <form className="sp-input-form" style={{ opacity: 0.5, pointerEvents: "none" }}>
                            <button type="button" className="sp-input-attach">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
                            </button>
                            <input type="text" className="sp-input-field" disabled placeholder="Ask a follow-up" />
                            <div className="sp-input-actions">
                                <button type="button" className="sp-model-btn">Model ▾</button>
                            </div>
                        </form>
                    </div>
                </div>
                <aside className="sp-sources-panel">
                    <div className="sp-sources-panel-header">
                        <div>
                            <h3 className="sp-sources-panel-title">Sources</h3>
                            <p className="sp-sources-panel-subtitle">Loading...</p>
                        </div>
                    </div>
                    <div className="sp-sources-empty">Finding top sources...</div>
                </aside>
            </div>
        </div>
    );
}

export default function SearchPage() {
    return (
        <Suspense fallback={<SearchPageSkeleton />}>
            <SearchPageContent />
        </Suspense>
    );
}
