"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowUp, ArrowUpRight, ChevronDown, FileSearch, FlaskConical, LoaderCircle, RefreshCw, ShieldCheck } from "lucide-react";
import { pharmaThumbnail, requestPharmaFeed } from "@/lib/pharmaFeed";
import { pharmaFieldText, pharmaFilters, readPharmaRecord, recordProvider, rememberPharmaRecord, type PharmaRecord } from "@/lib/pharmaRecord";
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
        <header className="pi-detail-nav"><Link className="pi-button" href={back} aria-label="Back to Pharma intelligence"><ArrowLeft size={15} /><span className="pi-detail-back-full">Pharma intelligence</span><span className="pi-detail-back-short">Pharma</span></Link>
            {record && <a className="pi-button" href={record.item.url} target="_blank" rel="noopener noreferrer">Original source<ArrowUpRight size={15} /><span className="sr-only"> (opens in a new tab)</span></a>}
        </header>
        {busy ? <div className="pi-detail-state" role="status"><LoaderCircle className="pi-spinning" size={24} /><p>Loading record…</p></div>
            : error ? <div className="pi-detail-state" role="alert"><FileSearch size={28} /><h1>Record unavailable</h1><p>{error}</p><button className="pi-button" onClick={() => void load()}>Retry</button></div>
            : record && <RecordView key={`${record.item.id}:${record.item.date}:${record.item.summary}`} record={record} />}
    </section>;
}

function RecordView({ record }: { record: PharmaRecord }) {
    const { item } = record, provider = recordProvider(record);
    const Icon = item.source === "fda" ? ShieldCheck : item.source === "trials" ? FlaskConical : FileSearch;
    return <div className="pi-detail-content">
        <header className="pi-detail-overview">
            <div className="pi-detail-heading"><div className="pi-detail-kicker"><span className={`pi-record-kind pi-tone-${item.source}`}><Icon size={14} aria-hidden="true" />{item.category}</span><span>{provider.name}</span></div>
                <h1>{item.title}</h1>
                <div className="pi-detail-meta"><span>{item.organization || "Organization not listed"}</span><span className="pi-detail-date">{item.date_label} · <time dateTime={item.date}>{date(item.date)}</time></span></div>
            </div>
        </header>
        <div className="pi-detail-layout"><RecordConversation record={record} /><RecordEvidence record={record} /></div>
    </div>;
}

function RecordEvidence({ record }: { record: PharmaRecord }) {
    const { item } = record, provider = recordProvider(record);
    const [expanded, setExpanded] = useState(() => typeof window !== "undefined" && window.matchMedia("(min-width: 1101px)").matches);
    useEffect(() => {
        const media = window.matchMedia("(min-width: 1101px)");
        const change = () => setExpanded(media.matches);
        media.addEventListener("change", change);
        return () => media.removeEventListener("change", change);
    }, []);
    const fields = item.source === "fda" ? ["application", "action", "ingredients"] : item.source === "trials" ? ["study_id", "status", "phases", "conditions", "interventions"] : [];
    return <aside className="pi-detail-facts" aria-label="Original record details">
            <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
                <summary><span>Source record</span><ChevronDown size={14} aria-hidden="true" /></summary>
                <div className="pi-detail-evidence-body">
                {item.source === "news" && pharmaThumbnail(item.thumbnail) && <RecordThumbnail item={item} />}
                <dl>
                {fields.map(name => { const value = item.details?.[name as keyof NonNullable<typeof item.details>]; return <div key={name}><dt>{LABELS[name]}</dt><dd>{pharmaFieldText(name, value)}</dd></div>; })}
                <div><dt>Organization</dt><dd>{item.organization || "Not listed"}</dd></div>
                </dl>
                {item.summary && <div className="pi-detail-description"><h3>Description</h3><p>{item.summary}</p></div>}
                <a className="pi-detail-source-link" href={item.url} target="_blank" rel="noopener noreferrer">{provider.name}<ArrowUpRight size={14} /><span className="sr-only"> (opens in a new tab)</span></a>
                <p className="pi-detail-checked">Checked {provider.checked_at ? new Date(provider.checked_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "time unavailable"}</p>
                {provider.status === "stale" && <p className="pi-status-attention">Previous snapshot · refresh unavailable</p>}
                </div>
            </details>
    </aside>;
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
        <div className="pi-detail-analysis-heading"><h2 id="pi-analysis-title">Analyst brief</h2><div className="pi-detail-analysis-actions">{chat.threadId && <Link className="pi-detail-refresh" href={`/search?focus=all&id=${chat.threadId}`}>Continue in Search<ArrowUpRight size={13} aria-hidden="true" /></Link>}<button className="pi-detail-refresh" onClick={chat.refresh} disabled={chat.busy || !chat.turns.length} title="Create a new brief from this source snapshot"><RefreshCw size={13} aria-hidden="true" />Refresh brief</button></div></div>
        {chat.turns.map((turn, i) => <div className="pi-detail-turn" key={i}>
            {i > 0 && <div className="pi-detail-question">{turn.query}</div>}
            <AnswerStream query={turn.query} content={turn.answer} isStreaming={false} sources={turn.sources} />
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
        <div className="pi-detail-followup"><div className="pi-detail-followup-inner"><form onSubmit={event => { event.preventDefault(); submit(input); }}>
            <label className="sr-only" htmlFor="pi-followup">Ask about this record</label>
            <input id="pi-followup" value={input} maxLength={16000} onChange={event => setInput(event.target.value)} placeholder="Ask about this record" disabled={chat.busy || !chat.turns.length} autoComplete="off" />
            <ModeMenu compact /><button type="submit" className="pi-detail-send" aria-label="Send follow-up" disabled={chat.busy || !chat.turns.length || !input.trim()}><ArrowUp size={17} /></button>
        </form></div></div>
    </section>;
}
