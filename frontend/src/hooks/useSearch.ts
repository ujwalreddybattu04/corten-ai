"use client";

import { useState, useEffect, useRef, useCallback } from "react";

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

export interface ThreadData {
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
    error: string | null;
    model: string;
    tokensUsed: number;
    thoughtTime: number;
    toolsUsed: string[];
    toolsSelected: string[];
}

export function useSearch(initialQuery: string, focusMode: string = "all", existingThreadId?: string) {
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

    // Animation loop to drip text into displayAnswer
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
    }, [state.isStreaming]);

    // --- PERSISTENCE EFFECT ---
    // Save thread to localStorage when streaming completes successfully
    useEffect(() => {
        // Only persist when search is totally finished, has content, and no error
        if (!state.isStreaming && !state.isConnecting && !state.error && state.answer) {
            if (typeof window === "undefined") return;

            const isPrivate = sessionStorage.getItem("corten_private_mode") === "true";
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

                const threadsJson = localStorage.getItem("corten_threads") || localStorage.getItem("orivanta_threads");
                let threads: ThreadData[] = threadsJson ? JSON.parse(threadsJson) : [];

                const existingIdx = threads.findIndex(t => t.id === currentThreadId);

                const threadToSave: ThreadData = {
                    id: currentThreadId,
                    title: existingIdx >= 0 && threads[existingIdx].title ? threads[existingIdx].title : state.query,
                    createdAt: existingIdx >= 0 ? threads[existingIdx].createdAt : Date.now(),
                    updatedAt: Date.now(),
                    query: state.query,
                    history: state.history,
                    answer: state.answer,
                    sources: state.sources,
                    images: state.images,
                    researchSteps: state.researchSteps,
                    thoughtTime: state.thoughtTime,
                };

                if (existingIdx >= 0) {
                    threads[existingIdx] = threadToSave;
                } else {
                    threads.unshift(threadToSave);
                }

                localStorage.setItem("corten_threads", JSON.stringify(threads));

                // Dispatch event so Sidebar knows to reload its list
                window.dispatchEvent(new Event("corten_threads_updated"));
            } catch (e) {
                console.error("[useSearch] Failed to persist thread:", e);
            }
        }
    }, [state.isStreaming, state.isConnecting, state.error, state.answer, state.query, state.history, state.sources, state.images, state.researchSteps, state.thoughtTime]);

    const runSearch = useCallback(async (q: string, focus: string, backendMessages?: any[], keepHistory?: SearchMessage[]) => {
        if (!q.trim()) return;

        // Abort any in-flight request
        abortRef.current?.abort();
        abortRef.current = new AbortController();

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
            error: null,
            toolsUsed: [],
            toolsSelected: [],
        }));

        try {
            const response = await fetch(`${API_BASE}/api/v1/search/stream`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ query: q, focus_mode: focus, messages: backendMessages || [] }),
                signal: abortRef.current.signal,
            });

            if (!response.ok) {
                throw new Error(`Search failed: ${response.status} ${response.statusText}`);
            }

            setState(prev => ({ ...prev, isConnecting: false }));

            const reader = response.body!.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || trimmed === "data: [DONE]") continue;

                    if (!trimmed.startsWith("data:")) continue;

                    try {
                        const jsonPayload = trimmed.startsWith("data: ") ? trimmed.slice(6) : trimmed.slice(5);
                        const json = JSON.parse(jsonPayload);

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
                    } catch (e) {
                        console.error("[useSearch] Failed to parse JSON line:", trimmed, e);
                    }
                }
            }

            // --- LLM TITLE GENERATION ---
            if (!keepHistory || keepHistory.length === 0) {
                fetch(`${API_BASE}/api/v1/search/title`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query: q }),
                })
                    .then(res => res.json())
                    .then(data => {
                        const isPrivate = typeof window !== "undefined" && sessionStorage.getItem("corten_private_mode") === "true";
                        if (data.title && !isPrivate) {
                            try {
                                const threadsJson = localStorage.getItem("corten_threads") || localStorage.getItem("orivanta_threads");
                                if (threadsJson) {
                                    const threads: ThreadData[] = JSON.parse(threadsJson);
                                    const currentId = threadIdRef.current;
                                    const threadIdx = threads.findIndex(t => t.id === currentId || t.query === q);
                                    if (threadIdx >= 0) {
                                        threads[threadIdx].title = data.title;
                                        localStorage.setItem("corten_threads", JSON.stringify(threads));
                                        window.dispatchEvent(new Event("corten_threads_updated"));
                                    }
                                }
                            } catch (e) {
                                console.error("Failed to update thread title:", e);
                            }
                        }
                    })
                    .catch(err => console.error("Title generation failed:", err));
            }

        } catch (err: unknown) {
            if (err instanceof Error && err.name === "AbortError") return;
            const msg = err instanceof Error ? err.message : "Search failed";
            setState(prev => ({
                ...prev,
                error: msg,
                isConnecting: false,
            }));
        } finally {
            setState(prev => ({ ...prev, isStreaming: false, isConnecting: false }));
        }
    }, []);

    const appendQuery = useCallback((newQuery: string) => {
        if (!newQuery.trim() || state.isConnecting || state.isStreaming) return;

        let newHistory = state.history;
        if (state.query && state.answer) {
            newHistory = [...state.history, {
                query: state.query,
                answer: state.answer,
                sources: state.sources,
                images: state.images,
                researchSteps: state.researchSteps,
                thoughtTime: state.thoughtTime
            }];
        }

        const backendMessages = newHistory.flatMap(msg => [
            { role: "user", content: msg.query },
            { role: "assistant", content: msg.answer }
        ]);

        runSearch(newQuery, focusMode, backendMessages, newHistory);
    }, [state, focusMode, runSearch]);

    useEffect(() => {
        // If we are passing an existing threadId, DO NOT run search, hydrate instead
        if (existingThreadId && !hasStarted.current) {
            if (typeof window !== "undefined") {
                const isPrivate = sessionStorage.getItem("corten_private_mode") === "true";
                if (!isPrivate) {
                    try {
                        const threadsJson = localStorage.getItem("corten_threads") || localStorage.getItem("orivanta_threads");
                        if (threadsJson) {
                            const threads: ThreadData[] = JSON.parse(threadsJson);
                            const thread = threads.find(t => t.id === existingThreadId);
                            if (thread) {
                                setState(prev => ({
                                    ...prev,
                                    threadId: thread.id,
                                    history: thread.history,
                                    query: thread.query,
                                    answer: thread.answer,
                                    sources: thread.sources,
                                    images: thread.images,
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
