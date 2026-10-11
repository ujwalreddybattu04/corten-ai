/** Read the entire summary stream, including its last unterminated SSE line. */
export interface ArticleSummaryEvent {
    type: string;
    content?: string;
    data?: string;
    message?: string;
    sources?: unknown[];
    items?: unknown[];
}

export async function readArticleSummary(
    response: Response,
    onEvent: (event: ArticleSummaryEvent) => void,
): Promise<string> {
    if (!response.ok || !response.body) {
        throw new Error("The summary service is temporarily unavailable. Please try again.");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let content = "";
    let completed = false;
    const consume = (line: string) => {
        if (completed || !line.startsWith("data:")) return;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") { completed = true; return; }
        let event: ArticleSummaryEvent;
        try { event = JSON.parse(payload); } catch { return; }
        if (!event || typeof event.type !== "string") return;
        if (event.type === "error") {
            throw new Error(event.message || "The summary could not be completed. Please retry.");
        }
        if (event.type === "token") {
            const token = event.content ?? event.data;
            if (typeof token === "string") content += token;
        }
        if (event.type === "done") completed = true;
        onEvent(event);
    };
    try {
        while (true) {
            const { done, value } = await reader.read();
            pending += done ? decoder.decode() : decoder.decode(value, { stream: true });
            const lines = pending.split("\n");
            pending = lines.pop() || "";
            for (const line of lines) consume(line);
            if (done) { consume(pending); break; }
            if (completed) break;
        }
        if (!completed || !content.trim()) {
            throw new Error("The summary connection ended before completion. Please retry.");
        }
        return content;
    } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
    }
}
