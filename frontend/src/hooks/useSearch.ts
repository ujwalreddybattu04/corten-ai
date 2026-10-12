"use client";
import { isPrivateChat } from "@/lib/questionDrafts";
import { accountStorage } from "@/lib/accountStorage";
import { readArticleSummary } from "@/lib/articleSummaryStream";
import { openSearchStream } from "@/lib/searchConnection";
import { associateSpaceThread } from "@/lib/spaces";


import { useState, useEffect, useRef, useCallback } from "react";
import { conversationMessages, ConversationMessage } from "@/lib/conversation";
import { prepareThreadTitle, scheduleThreadTitle, ThreadTitleMetadata } from "@/lib/threadTitles";

const API_BASE = typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? ""
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");

export interface SearchSource {
    url: string;
    title: string;
    domain: string;
    favicon?: string;
    faviconUrl?: string;
    snippet?: string;
    citationIndex: number;
}

export interface SearchImage {
    url: string;
    thumbnailUrl?: string;
    alt: string;
    sourceUrl?: string;
    source?: string;
}

export interface SearchMessage {
    query: string;
    answer: string;
    sources: SearchSource[];
    images: SearchImage[];
    researchSteps?: ResearchStep[];
    thoughtTime?: number;
}

export interface ThreadData extends ThreadTitleMetadata {
    id: string;
    title: string;
    createdAt: number;
    updatedAt: number;
    query: string;
    history: SearchMessage[];
    answer: string;
    sources: SearchSource[];
    images: SearchImage[];
    researchSteps?: ResearchStep[];
    thoughtTime?: number;
}

// Simple UUID generator for browser
function generateThreadId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

export interface ResearchStep {
    type: 'thought' | 'query_step' | 'status' | 'research_step' | 'research_progress' | 'tool_executing' | 'tool_result';
    content: string;
    detail?: string;
    step?: string;
    tool?: string;
}

export interface SearchState {
    threadId: string | null;
    history: SearchMessage[];
    query: string;
    answer: string;
    sources: SearchSource[];
    images: SearchImage[];
    researchSteps: ResearchStep[];
    relatedQuestions: string[];
    isStreaming: boolean;
    isConnecting: boolean;
    connectionMessage: string;
    error: string | null;
    model: string;
    tokensUsed: number;
    thoughtTime: number;
    toolsUsed: string[];
    toolsSelected: string[];
}

export function useSearch(initialQuery: string, focusMode: string = "all", existingThreadId?: string, spaceId?: string) {
    const [state, setState] = useState<SearchState>({
        threadId: existingThreadId || null,
        history: [],
        query: initialQuery,
        answer: "",
        sources: [],
        images: [],
        researchSteps: [],
        relatedQuestions: [],
        isStreaming: false,
        isConnecting: true,
        connectionMessage: "Connecting to Corten…",
        error: null,
        model: "Auto",
        tokensUsed: 0,
        thoughtTime: 0,
        toolsUsed: [],
        toolsSelected: [],
    });

    // --- BUTTERY SMOOTH STREAMING BUFFER ---
    const [displayAnswer, setDisplayAnswer] = useState("");
    const [isBufferDraining, setIsBufferDraining] = useState(false);
    const streamingBufferRef = useRef("");
    const animationFrameRef = useRef<number | null>(null);
    const lastUpdateTimeRef = useRef(0);

    const abortRef = useRef<AbortController | null>(null);
    const hasStarted = useRef(false);
    const lastProcessedQuery = useRef<string | null>(null);
    const threadIdRef = useRef<string | null>(existingThreadId || null);
    const hasAnswer = state.answer.length > 0;

    useEffect(() => () => {
        abortRef.current?.abort();
        // React development mode replays effects; allow that mount to restart.
        hasStarted.current = false;
    }, []);

    // Fast offline answers may finish in one React batch. The first token must
    // start the display buffer even if streaming=true never reached the screen.
    useEffect(() => {
        const updateDisplay = (timestamp: number) => {
            if (!lastUpdateTimeRef.current) lastUpdateTimeRef.current = timestamp;
            const progress = timestamp - lastUpdateTimeRef.current;

            // Update roughly every 30ms for "buttery" feel (Higher frequency for faster rendering)
            if (progress > 30 && streamingBufferRef.current.length > 0) {
                // Take a slice of the buffer. 
                // We take up to 12 chars or until the next space to keep it word-ish.
                let sliceEnd = 12;
                const nextSpace = streamingBufferRef.current.indexOf(" ", 8);
                if (nextSpace !== -1 && nextSpace < 20) {
                    sliceEnd = nextSpace + 1;
                }

                const slice = streamingBufferRef.current.slice(0, sliceEnd);
                streamingBufferRef.current = streamingBufferRef.current.slice(sliceEnd);

                setDisplayAnswer(prev => prev + slice);
                lastUpdateTimeRef.current = timestamp;
            }

            // Check if we still need to keep running
            const hasBufferContent = streamingBufferRef.current.length > 0;
            if (state.isStreaming || hasBufferContent) {
                setIsBufferDraining(hasBufferContent && !state.isStreaming);
                animationFrameRef.current = requestAnimationFrame(updateDisplay);
            } else {
                // Buffer is fully drained and streaming is done
                setIsBufferDraining(false);
            }
        };

        if (state.isStreaming || streamingBufferRef.current.length > 0) {
            setIsBufferDraining(true);
            animationFrameRef.current = requestAnimationFrame(updateDisplay);
        }

        return () => {
            if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        };
    }, [state.isStreaming, hasAnswer]);

    // --- PERSISTENCE EFFECT ---
    // Save thread to localStorage when streaming completes successfully
    useEffect(() => {
        // Only persist when search is totally finished, has content, and no error
        if (!state.isStreaming && !state.isConnecting && !state.error && state.answer) {
            if (typeof window === "undefined") return;

            const isPrivate = isPrivateChat();
            if (isPrivate) return;

            try {
                let currentThreadId = threadIdRef.current;
                if (!currentThreadId) {
                    currentThreadId = generateThreadId();
                    threadIdRef.current = currentThreadId;
                    // Expose the generated ID so consumers (e.g. ThreadMenu) can reference it
                    setState(prev =>
                        prev.threadId === currentThreadId ? prev : { ...prev, threadId: currentThreadId }
                    );
                }

                const threadsJson = accountStorage.getItem("corten_threads") || accountStorage.getItem("orivanta_threads");
                let threads: ThreadData[] = threadsJson ? JSON.parse(threadsJson) : [];

                const existingIdx = threads.findIndex(t => t.id === currentThreadId);

                const threadToSave = prepareThreadTitle<ThreadData>({
                    ...(existingIdx >= 0 ? threads[existingIdx] : {}),
                    id: currentThreadId,
                    title: existingIdx >= 0 ? threads[existingIdx].title : "",
                    createdAt: existingIdx >= 0 ? threads[existingIdx].createdAt : Date.now(),
                    updatedAt: Date.now(),
                    query: state.query,
                    history: state.history,
                    answer: state.answer,
                    sources: state.sources,
                    images: state.images,
                    researchSteps: state.researchSteps,
                    thoughtTime: state.thoughtTime,
                });

                if (existingIdx >= 0) {
                    threads[existingIdx] = threadToSave;
                } else {
                    threads.unshift(threadToSave);
                }

                accountStorage.setItem("corten_threads", JSON.stringify(threads));
                if (spaceId) associateSpaceThread(spaceId, currentThreadId);
                // Generate only after the exact thread exists. This survives navigation/remounts.
                scheduleThreadTitle(currentThreadId);

                // A reload must reopen this saved thread, including its follow-ups.
                const url = new URL(window.location.href);
                if (url.pathname === "/search" && url.searchParams.get("id") !== currentThreadId) {
                    url.searchParams.set("id", currentThreadId);
                    url.searchParams.delete("q");
                    url.searchParams.delete("draft");
                    // Next.js copies its router state for native navigation. Passing
                    // its internal state back would bypass the search-param update.
                    window.history.replaceState(null, "", url.toString());
                }

                // Dispatch event so Sidebar knows to reload its list
                window.dispatchEvent(new Event("corten_threads_updated"));
            } catch (e) {
                console.error("[useSearch] Failed to persist thread:", e);
            }
        }
    }, [state.isStreaming, state.isConnecting, state.error, state.answer, state.query, state.history, state.sources, state.images, state.researchSteps, state.thoughtTime, spaceId]);

    const runSearch = useCallback(async (q: string, focus: string, backendMessages?: ConversationMessage[], keepHistory?: SearchMessage[]) => {
        if (!q.trim()) return;

        // Abort any in-flight request
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        streamingBufferRef.current = "";
        setDisplayAnswer("");

        setState(prev => ({
            ...prev,
            history: keepHistory !== undefined ? keepHistory : prev.history,
            query: q,
            answer: "",
            sources: [],
            images: [],
            researchSteps: [],
            relatedQuestions: [],
            isStreaming: true,
            isConnecting: true,
            connectionMessage: "Connecting to Corten…",
            error: null,
            toolsUsed: [],
            toolsSelected: [],
        }));

        try {
            const response = await openSearchStream({ apiBase: API_BASE, query: q, focus, messages: backendMessages || [] },
                controller.signal, message => {
                    if (!controller.signal.aborted && abortRef.current === controller) {
                        setState(prev => ({ ...prev, connectionMessage: message }));
                    }
                });
            if (controller.signal.aborted || abortRef.current !== controller) return;

            setState(prev => ({ ...prev, isConnecting: false }));

            await readArticleSummary(response, (json: any) => {
                if (controller.signal.aborted || abortRef.current !== controller) return;
                        if (json.type === "token") {
                            const chunk = json.content || "";
                            streamingBufferRef.current += chunk;
                            setState(prev => ({ ...prev, answer: prev.answer + chunk }));
                        } else if (json.type === "sources") {
                            const sourcesList = json.sources || json.items || json.results || [];
                            setState(prev => ({ ...prev, sources: sourcesList }));
                        } else if (json.type === "images") {
                            setState(prev => ({ ...prev, images: json.images || [] }));
                        } else if (json.type === "related") {
                            setState(prev => ({ ...prev, relatedQuestions: json.questions || [] }));
                        } else if (json.type === "meta") {
                            setState(prev => ({
                                ...prev,
                                model: json.model || "Auto",
                                tokensUsed: json.tokens_used || 0,
                                toolsUsed: json.tools_used || prev.toolsUsed,
                            }));
                        } else if (json.type === "tools_selected") {
                            setState(prev => ({
                                ...prev,
                                toolsSelected: json.tools || [],
                            }));
                        } else if (json.type === "tool_executing") {
                            const toolName = json.tool || "";
                            const toolLabel = _toolDisplayName(toolName);
                            setState(prev => ({
                                ...prev,
                                researchSteps: [...prev.researchSteps, {
                                    type: 'tool_executing' as const,
                                    content: `Using ${toolLabel}`,
                                    tool: toolName,
                                }]
                            }));
                        } else if (json.type === "tool_result") {
                            const toolName = json.tool || "";
                            const toolLabel = _toolDisplayName(toolName);
                            const timeMs = json.execution_time_ms || 0;
                            setState(prev => ({
                                ...prev,
                                researchSteps: [...prev.researchSteps, {
                                    type: 'tool_result' as const,
                                    content: `${toolLabel} completed${timeMs ? ` (${timeMs}ms)` : ''}`,
                                    tool: toolName,
                                }]
                            }));
                        } else if (json.type === "thought" || json.type === "query_step" || json.type === "status") {
                            setState(prev => ({
                                ...prev,
                                researchSteps: [...prev.researchSteps, { type: json.type, content: json.content }]
                            }));
                        } else if (json.type === "research_start") {
                            setState(prev => ({
                                ...prev,
                                researchSteps: [
                                    ...prev.researchSteps,
                                    { type: 'status', content: 'Conducting deep research' },
                                ]
                            }));
                        } else if (json.type === "research_step") {
                            const step = json.step || "";
                            const detail = json.detail || "";
                            if (step === "Searching") {
                                setState(prev => ({
                                    ...prev,
                                    researchSteps: [...prev.researchSteps, { type: 'query_step', content: detail }]
                                }));
                            } else {
                                // Show only the detail — step name is internal
                                setState(prev => ({
                                    ...prev,
                                    researchSteps: [...prev.researchSteps, { type: 'thought', content: detail }]
                                }));
                            }
                        } else if (json.type === "research_progress") {
                            setState(prev => ({
                                ...prev,
                                researchSteps: [...prev.researchSteps, {
                                    type: 'status',
                                    content: json.status || 'Continuing research'
                                }]
                            }));
                        } else if (json.type === "thought_time") {
                            setState(prev => ({ ...prev, thoughtTime: json.time || 0 }));
                        } else if (json.type === "error") {
                            setState(prev => ({ ...prev, error: json.message || "Search failed" }));
                        }
            }, "answer");

        } catch (err: unknown) {
            if (controller.signal.aborted || abortRef.current !== controller) return;
            const msg = err instanceof Error ? err.message : "Search failed";
            setState(prev => ({
                ...prev,
                error: msg,
                isConnecting: false,
            }));
        } finally {
            if (!controller.signal.aborted && abortRef.current === controller) {
                setState(prev => ({ ...prev, isStreaming: false, isConnecting: false }));
            }
        }
    }, []);

    const appendQuery = useCallback((newQuery: string) => {
        if (!newQuery.trim() || state.isConnecting || state.isStreaming) return;

        let newHistory = state.history;
        if (state.query && state.answer && !state.error) {
            newHistory = [...state.history, {
                query: state.query,
                answer: state.answer,
                sources: state.sources,
                images: state.images,
                researchSteps: state.researchSteps,
                thoughtTime: state.thoughtTime
            }];
        }

        const backendMessages = conversationMessages(newHistory);

        runSearch(newQuery, focusMode, backendMessages, newHistory);
    }, [state, focusMode, runSearch]);

    const retrySearch = useCallback(() => {
        if (state.isConnecting || state.isStreaming || !state.query.trim()) return;
        void runSearch(state.query, focusMode, conversationMessages(state.history), state.history);
    }, [state, focusMode, runSearch]);

    useEffect(() => {
        // If we are passing an existing threadId, DO NOT run search, hydrate instead
        if (existingThreadId && !hasStarted.current) {
            if (typeof window !== "undefined") {
                const isPrivate = isPrivateChat();
                if (!isPrivate) {
                    try {
                        const threadsJson = accountStorage.getItem("corten_threads") || accountStorage.getItem("orivanta_threads");
                        if (threadsJson) {
                            const threads: ThreadData[] = JSON.parse(threadsJson);
                            const thread = threads.find(t => t.id === existingThreadId);
                            if (thread) {
                                setState(prev => ({
                                    ...prev,
                                    threadId: thread.id,
                                    history: Array.isArray(thread.history) ? thread.history : [],
                                    query: thread.query,
                                    answer: thread.answer,
                                    sources: thread.sources || [],
                                    images: thread.images || [],
                                    researchSteps: thread.researchSteps || [],
                                    thoughtTime: thread.thoughtTime || 0,
                                    isConnecting: false,
                                    isStreaming: false
                                }));
                                setDisplayAnswer(thread.answer);
                                threadIdRef.current = thread.id;
                                hasStarted.current = true;
                                lastProcessedQuery.current = thread.query;
                            }
                        }
                    } catch (e) {
                        console.error("Failed to load existing thread:", e);
                    }
                }
            }
            if (!hasStarted.current) {
                hasStarted.current = true;
                setState(prev => ({
                    ...prev,
                    isConnecting: false,
                    error: "This conversation is unavailable. Sign in to its account, retry cloud sync, or start a new thread."
                }));
            }
        }

        if (initialQuery && !hasStarted.current && !existingThreadId) {
            hasStarted.current = true;
            lastProcessedQuery.current = initialQuery;
            runSearch(initialQuery, focusMode);
        }
    }, [initialQuery, existingThreadId, focusMode, runSearch]);

    return {
        ...state,
        displayAnswer,
        isBufferDraining,
        isDisplayComplete: !state.isStreaming && !isBufferDraining,
        appendQuery,
        retrySearch,
    };
}

// ── Tool display names for UI ────────────────────────────────────────────────
const _TOOL_LABELS: Record<string, string> = {
    web_search: "Web Search",
    image_search: "Image Search",
    calculator: "Calculator",
    url_reader: "URL Reader",
    weather: "Weather",
    news_search: "News Search",
    academic: "Academic Search",
    video_search: "Video Search",
    code_runner: "Code Runner",
    finance: "Finance Data",
    translation: "Translator",
};

function _toolDisplayName(name: string): string {
    return _TOOL_LABELS[name] || name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
