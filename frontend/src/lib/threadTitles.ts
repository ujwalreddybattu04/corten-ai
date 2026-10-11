/** Titles live with the saved thread, independent of the streaming component's lifetime. */
export interface ThreadTitleMetadata {
    titleSource?: "pending" | "generated" | "fallback" | "manual";
    titleTopic?: string;
    titleRetryAt?: number;
    titleVersion?: number;
}

export interface TitleThread extends ThreadTitleMetadata {
    id: string;
    title: string;
    query: string;
    answer?: string;
    history?: Array<{ query: string; answer?: string }>;
    updatedAt?: number;
}

const KEY = "corten_threads";
const VERSION = 1;
const RETRY_DELAY = 60 * 60 * 1000;
const queue = new Set<string>();
const inFlight = new Set<string>();
let draining = false;

function isGreeting(query: string): boolean {
    return /^(?:hi|hello|hey|hello there|good (?:morning|afternoon|evening))(?:\s+(?:corten|there|assistant))?[\s!?.]*$/i.test(query.trim());
}

function titleContext(thread: TitleThread) {
    const turns = [...(Array.isArray(thread.history) ? thread.history : []), thread];
    const topic = turns.find(turn => typeof turn.query === "string" && turn.query.trim() && !isGreeting(turn.query)) || thread;
    return {
        query: (topic.query || "").trim().slice(0, 1600),
        answer: (topic.answer || "").slice(0, 1000),
        provisional: turns.every(turn => !turn.query?.trim() || isGreeting(turn.query)),
    };
}

export function fallbackThreadTitle(query: string): string {
    if (!query.trim() || isGreeting(query)) return "New Conversation";
    if (/\b(previous|last|first|earlier|past)\b.*\b(question|message|chat)\b/i.test(query)) return "Conversation Recap";
    if (/\b(code|coding|script|program|function)\b/i.test(query)) {
        const language = ["Python", "JavaScript", "TypeScript", "Java", "SQL", "Rust", "Go"].find(name => new RegExp(`\\b${name}\\b`, "i").test(query));
        if (language) return `${language} Coding`;
    }
    const stop = new Set("i me my you your we our a an the is are was were do does did can could would should please what whats who where when why how tell explain describe give show help about of to for and in on it this that need want write create make generate summarize summary regarding article remember keep mind has have with from".split(" "));
    const words = (query.replace(/https?:\/\/\S+/g, "").match(/[\p{L}\p{N}]+(?:[-'][\p{L}\p{N}]+)*/gu) || []).filter(word => !stop.has(word.toLowerCase())).slice(0, 5);
    if (!words.length) return "General Discussion";
    if (words.length === 1) words.push("Discussion");
    return words.map(word => word[0].toUpperCase() + word.slice(1)).join(" ").slice(0, 64).trim();
}

/** Conservatively repair raw legacy prompts; retain custom and already generated headings. */
export function prepareThreadTitle<T extends TitleThread>(thread: T): T {
    if (thread.titleSource === "manual") return thread;
    const context = titleContext(thread);
    if (thread.titleVersion === VERSION && thread.titleTopic === context.query) return thread;
    const turns = [...(thread.history || []), thread];
    const rawTitle = !thread.title || turns.some(turn => turn.query?.trim() === thread.title?.trim()) ||
        ["New Thread", "Corten Search", "New Conversation"].includes(thread.title);
    if (!thread.titleSource && !rawTitle) {
        // Legacy custom titles have no metadata: preserve them rather than guessing.
        return { ...thread, titleSource: "manual", titleVersion: VERSION };
    }
    return {
        ...thread,
        title: fallbackThreadTitle(context.query),
        titleSource: context.provisional ? "fallback" : "pending",
        titleTopic: context.query,
        titleVersion: VERSION,
        titleRetryAt: undefined,
    };
}

function isPrivate(): boolean {
    return typeof window === "undefined" || sessionStorage.getItem("corten_private_mode") === "true";
}

function readThreads(): TitleThread[] {
    const raw = localStorage.getItem(KEY) || localStorage.getItem("orivanta_threads");
    const threads = raw ? JSON.parse(raw) : [];
    return Array.isArray(threads) ? threads : [];
}

function needsTitle(thread: TitleThread): boolean {
    return thread.titleSource !== "manual" && thread.titleSource !== "generated" &&
        !titleContext(thread).provisional && (!thread.titleRetryAt || thread.titleRetryAt <= Date.now());
}

function validTitle(value: unknown, query: string): value is string {
    return typeof value === "string" && value === value.trim() && value.length <= 64 &&
        value.split(/\s+/).length >= 2 && value.split(/\s+/).length <= 6 &&
        !/[\n<>\[\]{}#*]/.test(value) && !/^https?:/i.test(value) &&
        !/^(who|what|where|when|why|how|can|could|please|write|tell|give|generate|summarize)\b/i.test(value) &&
        value.toLowerCase().replace(/[?.!]+$/, "") !== query.toLowerCase().replace(/[?.!]+$/, "");
}

async function generateSavedTitle(id: string): Promise<void> {
    if (isPrivate()) return;
    let context: ReturnType<typeof titleContext> | undefined;
    let previousTitle = "";
    let generated: string | undefined;
    let source: "generated" | "fallback" = "fallback";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
        const thread = readThreads().find(thread => thread.id === id);
        if (!thread || !needsTitle(thread)) return;
        context = titleContext(thread);
        previousTitle = thread.title;
        const apiBase = window.location.hostname === "localhost" ? (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") : "";
        const response = await fetch(`${apiBase}/api/v1/search/title`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: context.query, answer: context.answer }),
            signal: controller.signal,
        });
        if (response.ok) {
            const data = await response.json();
            if (validTitle(data.title, context.query)) {
                generated = data.title;
                source = data.source === "fallback" ? "fallback" : "generated";
            }
        }
    } catch {
        // Keep the useful local heading. Titles must never fail the conversation.
    } finally {
        clearTimeout(timeout);
    }
    if (!context || isPrivate()) return;
    try {
        // Re-read after awaiting: another answer, rename, deletion or thread may have changed.
        const threads = readThreads();
        const index = threads.findIndex(thread => thread.id === id);
        const current = threads[index];
        if (!current || current.titleSource === "manual" || current.title !== previousTitle ||
            titleContext(current).query !== context.query) return;
        threads[index] = {
            ...current,
            title: generated || current.title,
            titleSource: source,
            titleRetryAt: source === "fallback" ? Date.now() + RETRY_DELAY : undefined,
        };
        localStorage.setItem(KEY, JSON.stringify(threads));
        window.dispatchEvent(new Event("corten_threads_updated"));
    } catch { /* Storage unavailable or thread removed. */ }
}

async function drainQueue(): Promise<void> {
    if (draining) return;
    draining = true;
    try {
        while (queue.size) {
            const id = queue.values().next().value!;
            queue.delete(id);
            inFlight.add(id);
            try { await generateSavedTitle(id); } finally { inFlight.delete(id); }
            // A provisional greeting may have become a real topic while awaiting its old title.
            if (!isPrivate()) {
                try {
                    const latest = readThreads().find(thread => thread.id === id);
                    if (latest && needsTitle(latest)) queue.add(id);
                } catch { /* Ignore malformed storage. */ }
            }
        }
    } finally {
        draining = false;
    }
}

export function scheduleThreadTitle(id: string): void {
    if (isPrivate() || inFlight.has(id)) return;
    queue.add(id);
    void drainQueue();
}

/** Upgrade visible legacy history in small serial batches, avoiding a provider burst. */
export function refreshThreadTitles(limit = 7): TitleThread[] {
    const threads = readThreads();
    if (isPrivate()) return threads;
    const prepared = threads.map(prepareThreadTitle);
    if (prepared.some((thread, index) => thread !== threads[index])) {
        localStorage.setItem(KEY, JSON.stringify(prepared));
    }
    [...prepared].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
        .slice(0, limit).filter(needsTitle).forEach(thread => scheduleThreadTitle(thread.id));
    return prepared;
}
