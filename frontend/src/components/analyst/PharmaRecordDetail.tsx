"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowUp, ArrowUpRight, FileSearch, LoaderCircle } from "lucide-react";
import { requestPharmaFeed } from "@/lib/pharmaFeed";
import { pharmaFilters, readPharmaRecord, recordProvider, rememberPharmaRecord, type PharmaRecord } from "@/lib/pharmaRecord";
import { usePharmaAnalysis } from "@/hooks/usePharmaAnalysis";
import AnswerStream from "@/components/thread/AnswerStream";
import { ModeMenu } from "@/components/chat/ComposerControls";
import { RecordThumbnail } from "./PharmaWorkspace";

const LABELS: Record<string, string> = { application: "Application", action: "Action", ingredients: "Active ingredients", study_id: "Study ID", status: "Study status", phases: "Trial phases", conditions: "Conditions", interventions: "Interventions" };
function date(value: string) { return new Date(value + "T00:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }

export default function PharmaRecordDetail() {
    const params = useParams<{ id: string }>();
    const search = useSearchParams();
    const { topic, days } = pharmaFilters(search.toString());
    const [record, setRecord] = useState<PharmaRecord | null>(null);
    const [busy, setBusy] = useState(true);
    const [error, setError] = useState("");
    const request = useRef<AbortController | null>(null);
    const back = `/analyst-workspace?tool=pharma&topic=${topic}&days=${days}`;
    const load = useCallback(async () => {
        request.current?.abort();
        const abort = new AbortController(); request.current = abort;
        setBusy(true); setError(""); setRecord(null);
        try {
            const id = decodeURIComponent(params.id || "");
            if (!id || id.length > 240) throw new Error("This record link is invalid.");
            const cached = readPharmaRecord(id, topic, days);
            if (cached) { setRecord(cached); return; }
            const feed = await requestPharmaFeed(topic, days, abort.signal);
            if (abort.signal.aborted) return;
            const item = feed.items.find(i => i.id === id);
            if (!item) throw new Error("This record is no longer in the loaded feed. Return to Pharma intelligence to choose a current record.");
            rememberPharmaRecord(item, feed); setRecord({ item, feed });
        } catch (failure) {
            if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : "The record could not be loaded. Please retry.");
        } finally { if (request.current === abort) { request.current = null; setBusy(false); } }
    }, [params.id, topic, days]);
    useEffect(() => {
        const timer = setTimeout(() => void load(), 0);
        return () => { clearTimeout(timer); request.current?.abort(); request.current = null; };
    }, [load]);

    return <section className="pi-detail-page" aria-label="Pharma record analysis">
        <header className="pi-detail-nav"><Link className="pi-button" href={back}><ArrowLeft size={15} />Pharma intelligence</Link>
            {record && <a className="pi-button" href={record.item.url} target="_blank" rel="noopener noreferrer">Original source<ArrowUpRight size={15} /><span className="sr-only"> (opens in a new tab)</span></a>}
        </header>
        {busy ? <div className="pi-detail-state" role="status"><LoaderCircle className="pi-spinning" size={24} /><p>Loading record…</p></div>
            : error ? <div className="pi-detail-state" role="alert"><FileSearch size={28} /><h1>Record unavailable</h1><p>{error}</p><button className="pi-button" onClick={() => void load()}>Retry</button></div>
            : record && <RecordView key={`${record.item.id}:${record.item.date}:${record.item.summary}`} record={record} />}
    </section>;
}

function RecordView({ record }: { record: PharmaRecord }) {
    const { item } = record, provider = recordProvider(record);
    const fields = item.source === "fda" ? ["application", "action", "ingredients"] : item.source === "trials" ? ["study_id", "status", "phases", "conditions", "interventions"] : [];
    return <div className="pi-detail-content">
        <div className="pi-detail-overview">
            <RecordThumbnail item={item} featured />
            <div className="pi-detail-heading"><span className={`pi-record-kind pi-tone-${item.source}`}>{item.category}</span><h1>{item.title}</h1>
                <p className="pi-detail-byline">{item.organization || provider.name}</p>
                <p className="pi-detail-date">{item.date_label} · <time dateTime={item.date}>{date(item.date)}</time></p>
                {item.tags.length > 0 && <div className="pi-detail-tags">{item.tags.map((tag, i) => <span key={i}>{tag.replace(/^PHASE/, "Phase ")}</span>)}</div>}
            </div>
        </div>
        <section className="pi-detail-facts" aria-labelledby="pi-facts-title"><div className="pi-detail-facts-heading"><h2 id="pi-facts-title">Source record</h2><span>{provider.name}</span></div>
            {item.summary && <p>{item.summary}</p>}
            <details><summary>Record details</summary><dl>
                {fields.map(name => { const value = item.details?.[name as keyof NonNullable<typeof item.details>]; return <div key={name}><dt>{LABELS[name]}</dt><dd>{Array.isArray(value) ? value.map(v => v.replace(/^PHASE/, "Phase ")).join(" · ") || "Not listed" : value || "Not listed"}</dd></div>; })}
                <div><dt>Organization</dt><dd>{item.organization || "Not listed"}</dd></div>
                <div><dt>Checked</dt><dd>{provider.checked_at ? new Date(provider.checked_at).toLocaleString() : "Not available"}</dd></div>
                <div><dt>Snapshot</dt><dd>{provider.status === "stale" ? "Previous results · refresh unavailable" : "Loaded source record"}</dd></div>
            </dl></details>
        </section>
        <RecordConversation record={record} />
    </div>;
}

function RecordConversation({ record }: { record: PharmaRecord }) {
    const chat = usePharmaAnalysis(record);
    const [input, setInput] = useState("");
    const start = useRef<HTMLDivElement>(null);
    const submit = (query: string) => {
        const value = query.trim();
        if (!value || chat.busy || !chat.turns.length) return;
        setInput(""); void chat.ask(value);
        requestAnimationFrame(() => start.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" }));
    };
    const suggestions = record.item.source === "trials" ? ["What does this study phase mean?", "What should we verify before changing the forecast?"]
        : record.item.source === "fda" ? ["What does this FDA action mean?", "What are the possible forecasting implications?"]
        : ["What could this mean for the competitive landscape?", "What should we verify next?"];
    return <section className="pi-detail-conversation" aria-labelledby="pi-analysis-title">
        <div className="pi-detail-analysis-heading"><h2 id="pi-analysis-title">Analysis</h2><span>Corten</span></div>
        {chat.turns.map((turn, i) => <div className="pi-detail-turn" key={i}>
            {i > 0 && <div className="pi-detail-question">{turn.query}</div>}
            <AnswerStream content={turn.answer} isStreaming={false} sources={turn.sources} />
        </div>)}
        <div ref={start} className="pi-detail-current">
            {chat.busy && <>{chat.turns.length > 0 && <div className="pi-detail-question">{chat.question}</div>}
                <AnswerStream content={chat.answer} isStreaming sources={chat.sources} researchSteps={chat.steps} />
            </>}
            {chat.error && <div className="pi-detail-analysis-error" role="alert"><p>{chat.error}</p><button className="pi-button" onClick={chat.retry}>Retry analysis</button></div>}
        </div>
        {!chat.busy && chat.turns.length > 0 && <div className="pi-detail-suggestions" aria-label="Suggested follow-up questions">
            {(chat.related.length ? chat.related : suggestions).map(query => <button key={query} onClick={() => submit(query)}>{query}<ArrowUpRight size={14} /></button>)}
        </div>}
        <div className="pi-detail-followup"><form onSubmit={event => { event.preventDefault(); submit(input); }}>
            <label className="sr-only" htmlFor="pi-followup">Ask about this record</label>
            <input id="pi-followup" value={input} maxLength={16000} onChange={event => setInput(event.target.value)} placeholder="Ask about this record" disabled={chat.busy || !chat.turns.length} autoComplete="off" />
            <ModeMenu compact /><button type="submit" className="pi-detail-send" aria-label="Send follow-up" disabled={chat.busy || !chat.turns.length || !input.trim()}><ArrowUp size={17} /></button>
        </form></div>
    </section>;
}
