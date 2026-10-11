/** A report is successful only after a complete artifact and terminal event. */
export async function readReportStream(response: Response, onEvent: (event: any) => void): Promise<void> {
    if (!response.ok || !response.body) throw new Error("The report service is temporarily unavailable. Please retry.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "", finished = false;
    let artifact: any = null;
    const consume = (line: string) => {
        if (finished || !line.startsWith("data:")) return;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") { finished = true; return; }
        let event;
        try { event = JSON.parse(payload); } catch { return; }
        if (!event || typeof event.type !== "string") return;
        if (event.type === "error") throw new Error(event.message || "The report could not be completed. Please retry.");
        if (event.type === "report_complete") {
            if (typeof event.download_url !== "string" || !/^\/api\/v1\/report\/download\/[a-f0-9]{32}$/.test(event.download_url)) {
                throw new Error("The report did not return a valid download. Please retry.");
            }
            artifact = event;
            return;
        }
        if (event.type === "done") { finished = true; return; }
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
            if (finished) break;
        }
        if (!finished || !artifact) throw new Error("The report connection ended before completion. Please retry.");
        onEvent(artifact);
        onEvent({ type: "done" });
    } finally {
        await reader.cancel().catch(() => undefined);
        reader.releaseLock();
    }
}
