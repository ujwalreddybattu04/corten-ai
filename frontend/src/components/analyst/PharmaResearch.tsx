"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowUp, ArrowUpRight, BookOpen, Check, ChevronDown, Download, FlaskConical, LoaderCircle, Microscope, ShieldCheck, Square, Scale, Building2 } from "lucide-react";
import { usePharmaResearch } from "@/hooks/usePharmaResearch";
import { evidenceCsv, researchReport, type PharmaToolStep } from "@/lib/pharmaResearch";
import { saveDownload } from "@/lib/interpolationDisplay";
import { isPrivateChat } from "@/lib/questionDrafts";
import AnswerStream from "@/components/thread/AnswerStream";

const EXAMPLES = [
    { icon: FlaskConical, title: "Clinical development", query: "Find recent phase 3 luspatercept studies and summarize their current status and primary endpoints." },
    { icon: ShieldCheck, title: "Approvals & safety", query: "Review olanzapine FDA approval actions and current labeling warnings. Separate confirmed changes from missing detail." },
    { icon: BookOpen, title: "Scientific evidence", query: "Find recent publications about tofersen in ALS. Compare study designs and explain the evidence limitations." },
    { icon: Building2, title: "Competitive landscape", query: "Compare official recent luspatercept and imetelstat developments in myelodysplastic syndromes. Keep company claims attributed." },
    { icon: Scale, title: "Patents & access", query: "Find official patent and reimbursement information for Reblozyl. Distinguish patent listings from verified exclusivity and launch dates." },
    { icon: Microscope, title: "Drug intelligence", query: "Research Reblozyl: verify its ingredient, FDA records, trials and scientific publications. Summarize what each source establishes." },
];

export function PharmaToolProgress({ steps, status, busy = false }: { steps: PharmaToolStep[]; status?: string; busy?: boolean }) {
    if (!steps.length) return null;
    const completed = steps.filter(step => step.status !== "running").length;
    return <div className="pr-task-panel"><div className="pr-task-heading"><span>{busy ? <LoaderCircle size={14} className="pi-spinning" /> : <Check size={14} />}{busy ? status || "Checking sources" : "Source checks complete"}</span><small>{completed} / {steps.length}</small></div>
        <ul className="pr-tools" aria-label="Research tools">{steps.map(step => <li key={step.id} data-status={step.status}>
        {step.status === "running" ? <LoaderCircle size={13} className="pi-spinning" /> : step.status === "available" ? <Check size={13} /> : <span aria-hidden="true">—</span>}
        <span>{step.label}</span><small>{step.status === "running" ? "Checking" : step.status === "available" ? `${step.count ?? 0} record${step.count === 1 ? "" : "s"}` : step.status === "empty" ? "No matches" : "Unavailable"}</small>
    </li>)}</ul></div>;
}

export default function PharmaResearch() {
    const search = useSearchParams(), router = useRouter(), chat = usePharmaResearch(search.get("id") || "");
    const [input, setInput] = useState(""), [downloadError, setDownloadError] = useState("");
    const textarea = useRef<HTMLTextAreaElement>(null), latest = useRef<HTMLDivElement>(null);
    const end = useRef<HTMLDivElement>(null), composer = useRef<HTMLDivElement>(null), following = useRef(true);
    const last = chat.turns.at(-1);
    const submit = (query: string) => { if (!query.trim() || chat.busy) return; following.current = true; setInput(""); setDownloadError(""); void chat.ask(query); requestAnimationFrame(() => latest.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" })); };
    useEffect(() => { if (textarea.current) { textarea.current.style.height = "auto"; textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 180)}px`; } }, [input]);
    useEffect(() => {
        const wheel = (event: WheelEvent) => { if (event.deltaY < 0) following.current = false; };
        const pause = () => { following.current = false; };
        const key = (event: KeyboardEvent) => { if (["ArrowUp", "Home", "PageUp"].includes(event.key) && !(event.target instanceof HTMLTextAreaElement)) pause(); };
        window.addEventListener("wheel", wheel, { passive: true }); window.addEventListener("touchmove", pause, { passive: true }); window.addEventListener("keydown", key);
        return () => { window.removeEventListener("wheel", wheel); window.removeEventListener("touchmove", pause); window.removeEventListener("keydown", key); };
    }, []);
    useEffect(() => {
        if (!chat.busy || !chat.answer || !following.current) return;
        const frame = requestAnimationFrame(() => {
            if (!following.current || !end.current || !composer.current) return;
            const overflow = end.current.getBoundingClientRect().bottom - composer.current.getBoundingClientRect().top + 24;
            if (overflow > 0) window.scrollBy({ top: overflow, behavior: "instant" });
        });
        return () => cancelAnimationFrame(frame);
    }, [chat.busy, chat.answer]);
    const download = (kind: "csv" | "md") => {
        if (!last) return;
        try {
            saveDownload(new Blob([kind === "csv" ? evidenceCsv(chat.records, chat.coverage) : researchReport(last.query, last.answer, last.sources, chat.coverage)],
                { type: kind === "csv" ? "text/csv;charset=utf-8" : "text/markdown;charset=utf-8" }), `pharma-research-${new Date().toISOString().slice(0, 10)}.${kind}`);
        } catch { setDownloadError("The download could not be created. Please retry."); }
    };
    return <section className="pr-page" aria-label="Pharma research">
        <header className="pi-detail-nav"><Link className="pi-button" href="/analyst-workspace?tool=pharma"><ArrowLeft size={14} />Pharma intelligence</Link>
            <button className="pi-button" onClick={() => { chat.newResearch(); setInput(""); if (search.get("id")) router.push("/analyst-workspace/pharma/research"); }}>New research<ArrowUpRight size={14} /></button></header>
        <div className="pr-content"><header className="pr-heading"><span className="pr-eyebrow"><Microscope size={16} />Pharma research</span>
            {!chat.turns.length && !chat.busy && <><h1>What are you investigating?</h1><p>Ask about a drug, trial, approval, safety signal or competitor.</p></>}
        </header>
        {!chat.turns.length && !chat.busy && <div className="pr-examples">{EXAMPLES.map(({ icon: Icon, title, query }) => <button key={title} onClick={() => { setInput(query); textarea.current?.focus(); }}><Icon size={19} /><strong>{title}</strong><span>{query}</span><ArrowUpRight size={14} /></button>)}</div>}
        {chat.turns.map((turn, index) => <article className="pr-turn" key={index}><h2>{turn.query}</h2><PharmaToolProgress steps={turn.tools || []} /><AnswerStream content={turn.answer} sources={turn.sources} isStreaming={false} /></article>)}
        <div ref={latest} className="pr-current" aria-busy={chat.busy}>
            {chat.busy && <><h2>{chat.question}</h2><PharmaToolProgress steps={chat.steps} status={chat.answer ? "Presenting checked answer" : chat.status} busy />{!chat.answer ? <p className="pr-status" role="status"><LoaderCircle size={15} className="pi-spinning" />{chat.status}</p> : <AnswerStream content={chat.answer} sources={chat.sources} isStreaming />}</>}
            {chat.error && <div className="pi-detail-analysis-error" role="alert"><p>{chat.error}</p>{chat.question && <button className="pi-button" onClick={chat.retry}>Retry research</button>}</div>}
        </div>
        {!chat.busy && last && !chat.error && <>
            {!!chat.coverage.length && <details className="pr-evidence"><summary>Evidence & coverage<span>{chat.records.length} retrieved record{chat.records.length === 1 ? "" : "s"}<ChevronDown size={14} /></span></summary>
                {chat.coverage.map((item, i) => <p key={i}><strong>{item.tool.replaceAll("_", " ")}</strong> · {item.status}<br />{item.coverage}</p>)}
                {chat.records.map((item, i) => <a key={i} href={item.url} target="_blank" rel="noopener noreferrer">[{item.citation}] {item.title}<ArrowUpRight size={13} /></a>)}
            </details>}
            <div className="pr-exports"><button className="pi-button" onClick={() => download("md")}><Download size={14} />Report</button><button className="pi-button" disabled={!chat.records.length && !chat.coverage.length} onClick={() => download("csv")}><Download size={14} />Evidence CSV</button>
                <span>{isPrivateChat() ? "Private session" : chat.saved ? "Saved to your history" : "This conversation has not been saved"}</span></div>
        </>}
        {downloadError && <p role="alert">{downloadError}</p>}
        <div ref={end} /><div ref={composer} className="pr-composer"><form onSubmit={event => { event.preventDefault(); submit(input); }}><label className="sr-only" htmlFor="pharma-research-query">Ask Pharma research</label>
            <textarea id="pharma-research-query" ref={textarea} rows={2} value={input} maxLength={8000} placeholder="Ask Pharma research…" onChange={event => setInput(event.target.value)} onKeyDown={event => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); if (!chat.busy) event.currentTarget.form?.requestSubmit(); }
            }} />
            <div className="pr-composer-bar"><span>Official sources · Scientific literature</span><div>{chat.busy && chat.answer && <button type="button" className="pi-detail-show-full" onClick={chat.showFull}>Show full answer</button>}
                {chat.busy ? <button type="button" className="pr-send" aria-label="Stop research" onClick={chat.stop}><Square size={14} /></button> : <button type="submit" className="pr-send" aria-label="Send question" disabled={!input.trim()}><ArrowUp size={18} /></button>}</div></div>
        </form></div>
        </div>
    </section>;
}
