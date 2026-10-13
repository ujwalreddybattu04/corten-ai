import type { ConversationMessage } from "./conversation";

const UNAVAILABLE = "Corten is temporarily unavailable. Please try again in a moment.";
class ConnectionError extends Error {
    constructor(public retryable: boolean, public retryAfter = 0) { super(UNAVAILABLE); }
}
function delay(ms: number, signal: AbortSignal) {
    return new Promise<void>((resolve, reject) => {
        const cancelled = () => { clearTimeout(timer); reject(signal.reason); };
        const timer = setTimeout(() => { signal.removeEventListener("abort", cancelled); resolve(); }, ms);
        if (signal.aborted) cancelled();
        else signal.addEventListener("abort", cancelled, { once: true });
    });
}
export async function openSearchStream(
    request: { apiBase: string; query: string; focus: string; messages: ConversationMessage[]; spaceId?: string;
        mode?: string; attachments?: string[]; incognito?: boolean },
    signal: AbortSignal, onWait: (message: string) => void,
    options: { budgetMs?: number; attemptMs?: number; delayMs?: number; fetcher?: typeof fetch } = {},
): Promise<Response> {
    const fetcher = options.fetcher ?? fetch;
    const deadline = Date.now() + (options.budgetMs ?? 120000);
    let ready = false;
    onWait("Connecting to Corten…");
    // Only the inexpensive GET is retried. Generation POSTs are never replayed.
    for (let attempt = 0; attempt < 30 && Date.now() < deadline; attempt++) {
        signal.throwIfAborted();
        try {
            const response = await fetcher(`${request.apiBase}/api/v1/search/status`, {
                cache: "no-store", signal: AbortSignal.any([signal,
                    AbortSignal.timeout(Math.max(1, Math.min(options.attemptMs ?? 12000, deadline - Date.now())))]),
            });
            if (!response.ok) {
                const header = response.headers.get("Retry-After");
                const seconds = header && /^\d+(\.\d+)?$/.test(header) ? Number(header)
                    : header ? Math.max(0, (Date.parse(header) - Date.now()) / 1000) : 0;
                throw new ConnectionError([408, 429, 500, 502, 503, 504].includes(response.status),
                    Number.isFinite(seconds) ? seconds * 1000 : 0);
            }
            let data;
            try { data = await response.json(); } catch { throw new ConnectionError(true); }
            if (data?.status !== "ready") throw new ConnectionError(true);
            ready = true;
            break;
        } catch (error) {
            signal.throwIfAborted();
            if (error instanceof ConnectionError && !error.retryable) throw error;
            const pause = Math.max(options.delayMs ?? Math.min(5000, 1500 * (attempt + 1)),
                error instanceof ConnectionError ? error.retryAfter : 0);
            if (attempt === 29 || pause >= deadline - Date.now()) throw new ConnectionError(false);
            onWait("Connecting to Corten. The service may be starting—please wait…");
            await delay(pause, signal);
        }
    }
    if (!ready) throw new ConnectionError(false);
    signal.throwIfAborted();
    let response: Response;
    try {
        response = await fetcher(`${request.apiBase}/api/v1/search/stream`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: request.query, focus_mode: request.focus, messages: request.messages,
                ...(request.spaceId ? { space_id: request.spaceId } : {}),
                ...(request.mode && request.mode !== "auto" ? { mode: request.mode } : {}),
                ...(request.attachments?.length ? { attachments: request.attachments } : {}),
                ...(request.incognito ? { incognito: true } : {}) }), signal,
        });
    } catch {
        signal.throwIfAborted();
        throw new Error("The connection was interrupted. Your question is still here. Please retry.");
    }
    if (!response.ok) {
        if ([408, 429, 500, 502, 503, 504].includes(response.status)) {
            throw new Error(response.status === 429
                ? "The service is busy or its request limit was reached. Please wait a moment and retry."
                : UNAVAILABLE);
        }
        if (request.spaceId && (response.status === 403 || response.status === 404)) {
            // Space access is checked before answering: removed members or viewers get a clear reason.
            const detail = await response.json().then(body => body?.detail).catch(() => null);
            throw new Error(typeof detail === "string" && response.status === 403 ? detail
                : "This Space is no longer available to you. It may have been deleted or your access was removed.");
        }
        throw new Error(response.status === 401 ? "Your session expired. Please sign in again."
            : response.status === 422 ? "Please check your question and try again." : "The request could not be completed. Please retry.");
    }
    return response;
}
