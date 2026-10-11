export interface ConversationMessage {
    role: "user" | "assistant";
    content: string;
}

// Matches the backend's per-thread bounds. Displayed/saved history remains intact.
const MAX_TURNS = 60;
const MAX_MESSAGE_CHARS = 6000;

function boundedContent(content: string): string {
    if (content.length <= MAX_MESSAGE_CHARS) return content;
    const marker = "\n[message shortened]\n";
    const head = Math.floor((MAX_MESSAGE_CHARS - marker.length) * 2 / 3);
    return content.slice(0, head) + marker + content.slice(-(MAX_MESSAGE_CHARS - marker.length - head));
}

export function conversationMessages(history: { query: string; answer: string }[]): ConversationMessage[] {
    return history.slice(-MAX_TURNS).flatMap(turn => [
        { role: "user" as const, content: boundedContent(turn.query) },
        { role: "assistant" as const, content: boundedContent(turn.answer) },
    ]);
}
