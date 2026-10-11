import { accountStorage } from "./accountStorage";

export interface DiscoverArticle {
    id: string;
    title: string;
    description: string;
    url: string;
    image: string;
    publishedAt: string;
    source: { name: string; domain: string; favicon: string };
    isHero: boolean;
    category?: string;
}
export interface DiscoverFeed {
    articles: DiscoverArticle[];
    has_more: boolean;
    status: "available" | "empty" | "stale";
    fetched_at?: string;
    partial?: boolean;
}
const MAX_AGE = 6 * 60 * 60 * 1000;
const CACHE_PREFIX = "discover_feed_v1:";

function validArticle(value: unknown): value is DiscoverArticle {
    if (!value || typeof value !== "object") return false;
    const a = value as DiscoverArticle;
    return typeof a.id === "string" && typeof a.title === "string"
        && typeof a.url === "string" && /^https?:\/\//i.test(a.url)
        && !!a.source && typeof a.source.name === "string";
}

export function readSavedFeed(tab: string, now = Date.now()): DiscoverFeed | null {
    try {
        const data = JSON.parse(accountStorage.getItem(CACHE_PREFIX + tab) || "null");
        const age = now - Date.parse(data?.fetched_at);
        if (!Number.isFinite(age) || age < 0 || age > MAX_AGE || !Array.isArray(data?.articles)
            || !data.articles.length || !data.articles.every(validArticle)) return null;
        return { ...data, status: "stale" };
    } catch { return null; }
}

export function saveFeed(tab: string, feed: DiscoverFeed) {
    // Preserve the original fetch time: serving an old feed never makes it fresh.
    if (!feed.articles.length || feed.partial || !feed.fetched_at) return;
    try { accountStorage.setItem(CACHE_PREFIX + tab, JSON.stringify(feed)); }
    catch { /* Storage is optional; quota/privacy settings do not prevent live news. */ }
}

class NewsRequestError extends Error {
    constructor(public retryable: boolean, public retryAfter = 0) { super("News request failed"); }
}
function pause(ms: number, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
        const cancel = () => { clearTimeout(timer); reject(signal.reason); };
        const timer = setTimeout(() => { signal.removeEventListener("abort", cancel); resolve(); }, ms);
        if (signal.aborted) cancel();
        else signal.addEventListener("abort", cancel, { once: true });
    });
}

/** Retry only this read-only feed, with a deadline covering a sleeping backend. */
export async function requestDiscoverFeed(url: string, signal: AbortSignal,
    onRetry?: () => void, options: { budgetMs?: number; attemptMs?: number; fetcher?: typeof fetch } = {}): Promise<DiscoverFeed> {
    const deadline = Date.now() + (options.budgetMs ?? 90000);
    const fetcher = options.fetcher ?? fetch;
    for (let attempt = 0; attempt < 7; attempt++) {
        signal.throwIfAborted();
        const remaining = deadline - Date.now();
        if (remaining <= 0) break;
        try {
            const response = await fetcher(url, {
                cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.min(remaining, options.attemptMs ?? 18000)))]),
            });
            if (!response.ok) {
                const retryable = [408, 429, 500, 502, 503, 504].includes(response.status);
                const header = response.headers.get("Retry-After");
                const seconds = header && /^\d+(\.\d+)?$/.test(header) ? Number(header)
                    : header ? Math.max(0, (Date.parse(header) - Date.now()) / 1000) : 0;
                throw new NewsRequestError(retryable, Number.isFinite(seconds) ? seconds * 1000 : 0);
            }
            const data = await response.json();
            if (data.status === "unavailable") throw new NewsRequestError(true);
            if (!Array.isArray(data.articles) || !data.articles.every(validArticle)
                || !["available", "empty", "stale"].includes(data.status)) throw new NewsRequestError(false);
            return data as DiscoverFeed;
        } catch (error) {
            signal.throwIfAborted();
            if (error instanceof NewsRequestError && !error.retryable) throw error;
            const wait = Math.max(Math.min(8000, 2000 * (attempt + 1)), error instanceof NewsRequestError ? error.retryAfter : 0);
            // Do not ignore Retry-After by retrying earlier than the server permits.
            if (attempt === 6 || wait >= deadline - Date.now()) throw error;
            onRetry?.();
            await pause(wait, signal);
        }
    }
    throw new Error("News connection timed out");
}
