import { useState, useCallback } from "react";

interface StreamingState {
    content: string;
    sources: any[];
    isStreaming: boolean;
    error: string | null;
}

export function useStreamingResponse() {
    const [state, setState] = useState<StreamingState>({
        content: "",
        sources: [],
        isStreaming: false,
        error: null,
    });

    const startStream = useCallback(async (url: string, body: object) => {
        setState({ content: "", sources: [], isStreaming: true, error: null });

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });

            if (!response.ok) throw new Error("Stream request failed");

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) throw new Error("No response body");

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split("\n").filter((line) => line.startsWith("data: "));

                for (const line of lines) {
                    const data = JSON.parse(line.slice(6));

                    if (data.type === "token") {
                        setState((prev) => ({ ...prev, content: prev.content + data.content }));
                    } else if (data.type === "sources") {
                        setState((prev) => ({ ...prev, sources: data.items }));
                    } else if (data.type === "done") {
                        setState((prev) => ({ ...prev, isStreaming: false }));
                    }
                }
            }
        } catch (error) {
            setState((prev) => ({
                ...prev,
                isStreaming: false,
                error: error instanceof Error ? error.message : "Unknown error",
            }));
        }
    }, []);

    return { ...state, startStream };
}
