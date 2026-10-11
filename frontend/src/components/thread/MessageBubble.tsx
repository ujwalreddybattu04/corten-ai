import type { Source } from "@/types/thread";
import { BRAND_NAME } from "@/config/constants";

interface MessageBubbleProps {
    role: "user" | "assistant";
    content: string;
    sources?: Source[];
    modelUsed?: string;
    timestamp?: string;
}

export default function MessageBubble({
    role,
    content,
    sources = [],
    modelUsed,
    timestamp,
}: MessageBubbleProps) {
    return (
        <div className={`message-bubble message-${role}`}>
            <div className="message-header">
                <span className="message-role">{role === "user" ? "You" : BRAND_NAME}</span>
                {modelUsed && <span className="message-model">{modelUsed}</span>}
                {timestamp && <span className="message-timestamp">{timestamp}</span>}
            </div>
            <div className="message-content">
                {/* Render markdown content with CitationBadge inline */}
                {content}
            </div>
            {sources.length > 0 && (
                <div className="message-sources">
                    {/* SourceCard components for this message */}
                </div>
            )}
        </div>
    );
}
