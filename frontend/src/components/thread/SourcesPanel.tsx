import type { Source } from "@/types/thread";
import SourceCard from "./SourceCard";

interface SourcesPanelProps {
    sources: Source[];
}

export default function SourcesPanel({ sources }: SourcesPanelProps) {
    if (sources.length === 0) return null;

    return (
        <div className="sources-panel" id="sources-panel">
            <h3 className="sources-panel-title">Sources</h3>
            <div className="sources-panel-list">
                {sources.map((source, index) => (
                    <SourceCard
                        key={source.id || index}
                        index={index + 1}
                        title={source.title}
                        url={source.url}
                        domain={source.domain}
                        faviconUrl={source.faviconUrl}
                        snippet={source.snippet}
                    />
                ))}
            </div>
        </div>
    );
}
