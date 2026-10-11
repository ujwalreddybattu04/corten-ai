"use client";

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, ChevronDown, Loader2, Calculator, CloudSun, Link2, Wrench, Check } from 'lucide-react';
import { ResearchStep, SearchSource } from '@/hooks/useSearch';
import { Favicon } from '@/components/common';
import '../../styles/research.css';

function _getToolIcon(toolName: string, size: number, className = "rp-tool-icon") {
    switch (toolName) {
        case 'calculator': return <Calculator size={size} className={className} />;
        case 'weather': return <CloudSun size={size} className={className} />;
        case 'url_reader': return <Link2 size={size} className={className} />;
        case 'web_search': return <Search size={size} className={className} />;
        default: return <Wrench size={size} className={className} />;
    }
}

// ── Animated Header Text — REAL backend events + live source domains ────────
// Phase 1: Shows real backend status messages (before sources arrive)
// Phase 2: Once sources arrive, rapidly cycles through "Reading domain.com"

function AnimatedThinkingText({ messages, sources, isActive }: {
    messages: string[];
    sources: SearchSource[];
    isActive: boolean;
}) {
    const [displayedText, setDisplayedText] = useState("");
    const [isTyping, setIsTyping] = useState(true);
    const intervalRef = useRef<NodeJS.Timeout | null>(null);
    const charRef = useRef(0);
    const shownCountRef = useRef(0);
    const [currentMsg, setCurrentMsg] = useState("Thinking");
    const domainCycleRef = useRef<NodeJS.Timeout | null>(null);
    const domainIdxRef = useRef(0);

    // Build the display message: prefer source domains when available
    const sourceDomains = useMemo(() => {
        return sources
            .map(s => (s.domain || '').replace(/^www\./, ''))
            .filter(d => d.length > 0);
    }, [sources]);

    // Phase 2: Cycle rapidly through real source domains
    useEffect(() => {
        if (!isActive || sourceDomains.length === 0) {
            if (domainCycleRef.current) clearInterval(domainCycleRef.current);
            return;
        }

        // Immediately show first domain
        domainIdxRef.current = 0;
        setCurrentMsg(`Reading ${sourceDomains[0]}`);

        domainCycleRef.current = setInterval(() => {
            domainIdxRef.current = (domainIdxRef.current + 1) % sourceDomains.length;
            setCurrentMsg(`Reading ${sourceDomains[domainIdxRef.current]}`);
        }, 1400); // cycle every 1.4s — fast but readable

        return () => {
            if (domainCycleRef.current) clearInterval(domainCycleRef.current);
        };
    }, [isActive, sourceDomains]);

    // Phase 1: Show real backend messages when no sources yet
    useEffect(() => {
        if (sourceDomains.length > 0) return; // Phase 2 handles it
        if (messages.length > 0 && messages.length > shownCountRef.current) {
            shownCountRef.current = messages.length;
            setCurrentMsg(messages[messages.length - 1]);
        }
    }, [messages.length, sourceDomains.length]);

    // Typewriter effect for each message change
    useEffect(() => {
        if (!isActive) return;

        charRef.current = 0;
        setDisplayedText("");
        setIsTyping(true);

        intervalRef.current = setInterval(() => {
            charRef.current++;
            if (charRef.current <= currentMsg.length) {
                setDisplayedText(currentMsg.slice(0, charRef.current));
            } else {
                setIsTyping(false);
                if (intervalRef.current) clearInterval(intervalRef.current);
            }
        }, 12); // ultra-fast typewriter

        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, [currentMsg, isActive]);

    // Reset on deactivation
    useEffect(() => {
        if (!isActive) {
            setDisplayedText("");
            charRef.current = 0;
            shownCountRef.current = 0;
            domainIdxRef.current = 0;
            if (domainCycleRef.current) clearInterval(domainCycleRef.current);
        }
    }, [isActive]);

    if (!isActive) return null;

    return (
        <span className="thinking-text-animated">
            <span className="thinking-text-shimmer">{displayedText}</span>
            <span className="thinking-cursor" />
        </span>
    );
}

// ── Source Title Ticker — cycles real article titles being analyzed ───────────
// Only appears once sources arrive. Header shows domains, this shows titles.

function SourceTitleTicker({ sources }: { sources: SearchSource[] }) {
    const [idx, setIdx] = useState(0);
    const cycleRef = useRef<NodeJS.Timeout | null>(null);

    const titles = useMemo(() => {
        return sources
            .map(s => s.title || '')
            .filter(t => t.length > 0);
    }, [sources]);

    useEffect(() => {
        if (titles.length === 0) return;
        setIdx(0);
        cycleRef.current = setInterval(() => {
            setIdx(prev => (prev + 1) % titles.length);
        }, 1200);
        return () => { if (cycleRef.current) clearInterval(cycleRef.current); };
    }, [titles]);

    if (titles.length === 0) return null;

    return (
        <div className="rp-live-ticker">
            <div className="rp-live-ticker-dot" />
            <AnimatePresence mode="wait">
                <motion.span
                    key={idx}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.18 }}
                    className="rp-live-ticker-text"
                >
                    {titles[idx]}
                </motion.span>
            </AnimatePresence>
        </div>
    );
}

// ── Main Component ──────────────────────────────────────────────────────────

interface ResearchProgressProps {
    query?: string;
    steps: ResearchStep[];
    isComplete: boolean;
    isStreaming?: boolean;
    isAnswerStarted?: boolean;
    sources?: SearchSource[];
    thoughtTime?: number;
}

export const ResearchProgress: React.FC<ResearchProgressProps> = ({
    query = "",
    steps,
    isComplete,
    isStreaming = false,
    isAnswerStarted = false,
    sources = [],
    thoughtTime = 0
}) => {
    const [isExpanded, setIsExpanded] = useState(true);
    const hasAutoCollapsed = useRef(false);

    // Timer logic
    const [localTime, setLocalTime] = useState(0);
    const startTimeRef = useRef<number | null>(null);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    // Auto-collapse when answer content starts appearing
    useEffect(() => {
        if (isAnswerStarted && !hasAutoCollapsed.current) {
            setIsExpanded(false);
            hasAutoCollapsed.current = true;
        }
    }, [isAnswerStarted]);

    // Timer effect
    useEffect(() => {
        if (!isStreaming && steps.length === 0) {
            setLocalTime(0);
            startTimeRef.current = null;
            if (timerRef.current) clearInterval(timerRef.current);
            return;
        }

        if (thoughtTime > 0) {
            if (timerRef.current) clearInterval(timerRef.current);
            setLocalTime(thoughtTime);
            return;
        }

        if (isStreaming && !isAnswerStarted) {
            if (!startTimeRef.current || steps.length === 1) {
                if (steps.length === 1 && startTimeRef.current) {
                    startTimeRef.current = Date.now();
                } else if (!startTimeRef.current) {
                    startTimeRef.current = Date.now();
                }

                if (timerRef.current) clearInterval(timerRef.current);
                timerRef.current = setInterval(() => {
                    if (startTimeRef.current) {
                        setLocalTime((Date.now() - startTimeRef.current) / 1000);
                    }
                }, 50);
            }
        }

        if (isAnswerStarted) {
            if (timerRef.current) {
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
            if (startTimeRef.current && thoughtTime === 0) {
                setLocalTime((Date.now() - startTimeRef.current) / 1000);
            }
        }

        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [isAnswerStarted, isStreaming, steps.length, thoughtTime]);

    // Reset auto-collapse tracker for new queries
    useEffect(() => {
        if (steps.length === 0) {
            hasAutoCollapsed.current = false;
            setIsExpanded(true);
        }
    }, [steps.length]);

    if (steps.length === 0 && !isStreaming) return null;

    // --- Classify steps ---
    // Filter out the first query_step (user's original query — already visible in chat bubble)
    const allQuerySteps = steps.filter(s => s.type === 'query_step');
    const querySteps = allQuerySteps.length > 1 ? allQuerySteps.slice(1) : [];
    const toolSteps = steps.filter(s => s.type === 'tool_executing' || s.type === 'tool_result');

    const displayTime = thoughtTime > 0 ? thoughtTime : localTime;
    const isThinking = !isAnswerStarted && !isComplete;
    const isDone = isAnswerStarted || isComplete;

    // Completed steps count
    const completedStepCount = steps.length;

    // Build live message feed from REAL backend events for header animation
    // Once sources arrive, header switches to domain cycling — these are pre-source messages only
    const liveMessages = useMemo(() => {
        const msgs: string[] = [];
        for (const step of steps) {
            if (step.content && (step.type === 'status' || step.type === 'thought' || step.type === 'tool_executing' || step.type === 'tool_result')) {
                msgs.push(step.content);
            }
        }
        return msgs;
    }, [steps]);

    return (
        <div className="research-container">
            {/* ───────── HEADER ───────── */}
            <div
                className="thinking-header"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="thinking-dot-container">
                    <div className={`thinking-dot ${isDone ? 'complete' : ''}`} />
                    {isThinking && <div className="thinking-dot-pulse" />}
                </div>

                {/* Dynamic animated text while thinking, source summary when done */}
                {isThinking ? (
                    <AnimatedThinkingText messages={liveMessages} sources={sources} isActive={isThinking} />
                ) : (
                    <span className="thinking-text-static">
                        {(() => {
                            // Tools used
                            const toolNames = [...new Set(
                                toolSteps
                                    .map(s => (s.tool || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))
                                    .filter(t => t.length > 0)
                            )];
                            const toolStr = toolNames.length > 0 ? toolNames.join(', ') : '';

                            // Source domains
                            const domains = sources
                                .map(s => (s.domain || '').replace(/^www\./, ''))
                                .filter(d => d.length > 0);

                            const timeStr = displayTime > 0 ? `${displayTime.toFixed(1)}s` : '';

                            const parts: string[] = [];
                            if (toolStr) parts.push(toolStr);
                            if (domains.length > 0) {
                                const shown = domains.slice(0, 2).join(', ');
                                const extra = domains.length > 2 ? ` +${domains.length - 2} more` : '';
                                parts.push(`${shown}${extra}`);
                            }
                            if (timeStr) parts.push(timeStr);

                            return parts.length > 0 ? parts.join(' · ') : `Completed ${completedStepCount} steps`;
                        })()}
                    </span>
                )}

                <ChevronDown
                    size={14}
                    className={`thinking-chevron ${isExpanded ? 'expanded' : ''}`}
                />
            </div>

            {/* ───────── EXPANDABLE CONTENT ───────── */}
            <AnimatePresence initial={false}>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                        style={{ overflow: 'hidden' }}
                    >
                        <div className="research-content">

                            {/* ── Source title ticker — cycles real article titles ── */}
                            {isThinking && sources.length > 0 && (
                                <SourceTitleTicker sources={sources} />
                            )}

                            {/* ── Tools Phase — unified status rows ── */}
                            {toolSteps.length > 0 && (() => {
                                // Merge executing + result into unified tool entries
                                const toolMap = new Map<string, { name: string; status: 'running' | 'done'; timeMs?: number }>();
                                for (const step of toolSteps) {
                                    const toolName = step.tool || 'unknown';
                                    if (step.type === 'tool_executing') {
                                        toolMap.set(toolName, { name: toolName, status: 'running' });
                                    } else if (step.type === 'tool_result') {
                                        const timeMatch = step.content.match(/\((\d+)ms\)/);
                                        toolMap.set(toolName, {
                                            name: toolName,
                                            status: 'done',
                                            timeMs: timeMatch ? parseInt(timeMatch[1]) : undefined,
                                        });
                                    }
                                }
                                const tools = Array.from(toolMap.values());

                                return (
                                    <div className="research-section">
                                        <div className="rp-tools-grid">
                                            {tools.map((tool, index) => (
                                                <motion.div
                                                    key={`tool-${tool.name}`}
                                                    initial={{ opacity: 0, y: 6 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    transition={{
                                                        type: "spring",
                                                        stiffness: 400,
                                                        damping: 30,
                                                        delay: index * 0.08,
                                                    }}
                                                    className={`rp-tool-row ${tool.status === 'done' ? 'rp-tool-row-done' : 'rp-tool-row-running'}`}
                                                >
                                                    <div className="rp-tool-row-icon">
                                                        {_getToolIcon(tool.name, 13)}
                                                    </div>
                                                    <span className="rp-tool-row-name">
                                                        {tool.name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                                                    </span>
                                                    <div className="rp-tool-row-status">
                                                        {tool.status === 'running' ? (
                                                            <Loader2 size={11} className="animate-spin" />
                                                        ) : (
                                                            <>
                                                                {tool.timeMs !== undefined && (
                                                                    <span className="rp-tool-row-time">{tool.timeMs < 1000 ? `${tool.timeMs}ms` : `${(tool.timeMs / 1000).toFixed(1)}s`}</span>
                                                                )}
                                                                <Check size={12} className="rp-tool-row-check" />
                                                            </>
                                                        )}
                                                    </div>
                                                </motion.div>
                                            ))}
                                        </div>
                                    </div>
                                );
                            })()}

                            {/* ── Searching Phase — query pills ── */}
                            {querySteps.length > 0 && (
                                <div className="research-section">
                                    <div className="research-label">Searching</div>
                                    <div className="rp-search-queries">
                                        {querySteps.map((step, index) => (
                                            <motion.div
                                                key={`query-${index}`}
                                                layout
                                                initial={{ opacity: 0, scale: 0.95, y: 5 }}
                                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                                transition={{
                                                    type: "spring",
                                                    stiffness: 300,
                                                    damping: 30,
                                                    delay: index * 0.06
                                                }}
                                                className="rp-search-pill"
                                            >
                                                <Search size={12} className="rp-search-pill-icon" />
                                                <span>{step.content}</span>
                                            </motion.div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* ── Reviewing Sources ── */}
                            {sources.length > 0 && (
                                <div className="research-section">
                                    <div className="research-label rp-reviewing-label">
                                        {isThinking && (
                                            <Loader2 size={11} className="animate-spin rp-reviewing-spinner" />
                                        )}
                                        Reviewing sources
                                    </div>
                                    <div className="rp-sources-list">
                                        {sources.map((source, index) => (
                                            <motion.a
                                                key={`rsrc-${index}`}
                                                href={source.url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                initial={{ opacity: 0, x: -8 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: index * 0.04, duration: 0.25 }}
                                                className="rp-source-row"
                                            >
                                                <div className="rp-source-favicon">
                                                    <Favicon url={source.url} domain={source.domain || ''} size={18} />
                                                </div>
                                                <span className="rp-source-title">{source.title}</span>
                                                <span className="rp-source-domain">{source.domain?.replace(/^www\./, '')}</span>
                                            </motion.a>
                                        ))}
                                    </div>
                                </div>
                            )}

                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};
