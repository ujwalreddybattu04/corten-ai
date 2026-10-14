"use client";

import { useId, useState } from "react";
import { ArrowUpRight, FileText, Plus, X } from "lucide-react";
import AnswerStream from "@/components/thread/AnswerStream";
import type { SearchSource } from "@/hooks/useSearch";

/** Keep the evidence beside its answer, including when a conversation has many turns. */
export default function PharmaAnswer({ content, sources, streaming = false, query = "" }: {
    content: string; sources: SearchSource[]; streaming?: boolean; query?: string;
}) {
    const [open, setOpen] = useState(false);
    const panelId = useId();
    const evidence = sources.flatMap((source, index) => {
        try {
            const url = new URL(source.url);
            if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return [];
            return [{ ...source, domain: url.hostname.replace(/^www\./, ""), number: source.citationIndex || index + 1 }];
        } catch { return []; }
    });
    return <div className="pa-answer">
        <AnswerStream query={query} content={content} isStreaming={streaming} sources={sources}
            sourcesPanelOpen={open} sourcesPanelId={panelId} setSourcesPanelOpen={setOpen} />
        {open && <section id={panelId} className="pa-sources" aria-label="Sources for this answer">
            <div className="pa-sources-heading"><h3>Sources <span>{evidence.length}</span></h3><button type="button" aria-label="Close sources" onClick={() => setOpen(false)}><X size={16} /></button></div>
            <ol>{evidence.map(source => <li key={`${source.number}:${source.url}`}><span className="pa-source-number">{source.number}</span>
                <a href={source.url} target="_blank" rel="noopener noreferrer"><span className="pa-source-domain"><FileText size={12} />{source.domain}</span><strong>{source.title || source.domain}</strong><ArrowUpRight size={15} /><span className="sr-only"> (opens in a new tab)</span></a>
            </li>)}</ol>
        </section>}
    </div>;
}

export function PharmaRelated({ questions, onSelect }: { questions: string[]; onSelect: (question: string) => void }) {
    if (!questions.length) return null;
    return <section className="pa-related" aria-label="Related questions"><h3>Related</h3>
        {questions.map(question => <button type="button" key={question} onClick={() => onSelect(question)}><span>{question}</span><Plus size={18} strokeWidth={1.5} aria-hidden="true" /></button>)}
    </section>;
}
