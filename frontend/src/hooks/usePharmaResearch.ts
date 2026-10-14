"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getStorageAccount } from "@/lib/accountStorage";
import { readArticleSummary } from "@/lib/articleSummaryStream";
import { progressiveText } from "@/lib/progressiveText";
import { openPharmaResearch, researchEvidence, researchSources, researchTool, restoreResearchThread, saveResearchThread, type PharmaCoverage, type PharmaEvidence, type PharmaToolStep } from "@/lib/pharmaResearch";
import type { PharmaTurn } from "@/lib/pharmaRecord";
import type { SearchSource } from "@/hooks/useSearch";

export function usePharmaResearch(existingId: string) {
    const [turns, setTurns] = useState<PharmaTurn[]>([]), [answer, setAnswer] = useState(""), [question, setQuestion] = useState("");
    const [sources, setSources] = useState<SearchSource[]>([]), [steps, setSteps] = useState<PharmaToolStep[]>([]);
    const [records, setRecords] = useState<PharmaEvidence[]>([]), [coverage, setCoverage] = useState<PharmaCoverage[]>([]);
    const [busy, setBusy] = useState(false), [status, setStatus] = useState(""), [error, setError] = useState(""), [saved, setSaved] = useState(false);
    const abort = useRef<AbortController | null>(null), reveal = useRef<ReturnType<typeof progressiveText> | null>(null);
    const prior = useRef<PharmaTurn[]>([]), owner = useRef(getStorageAccount()), id = useRef(""), pending = useRef("");
    useEffect(() => {
        const timer = setTimeout(() => {
            owner.current = getStorageAccount(); id.current = existingId || crypto.randomUUID();
            const restored = restoreResearchThread(existingId);
            prior.current = restored ? [...restored.history, restored].map(t => ({ query: t.query, answer: t.answer, sources: researchSources(t.sources) })) : [];
            setTurns(prior.current); setSaved(!!restored); setAnswer(""); setQuestion(""); setRecords([]); setCoverage([]); setSteps([]);
            setError(existingId && !restored ? "This research conversation is unavailable in this account or private session." : "");
        }, 0);
        return () => { clearTimeout(timer); abort.current?.abort(); abort.current = null; };
    }, [existingId]);
    const run = useCallback(async (value: string) => {
        const query = value.trim();
        if (abort.current || !query || query.length > 8000) return;
        const controller = new AbortController(); abort.current = controller; pending.current = query;
        const previous = [...prior.current]; let refs: SearchSource[] = [];
        const current = () => abort.current === controller && !controller.signal.aborted && owner.current === getStorageAccount();
        setBusy(true); setError(""); setQuestion(query); setAnswer(""); setSources([]); setSteps([]); setRecords([]); setCoverage([]); setStatus("Choosing Pharma sources");
        const display = progressiveText(text => { if (current()) setAnswer(text); }, controller.signal); reveal.current = display;
        try {
            const response = await openPharmaResearch(query, previous, controller.signal);
            const text = await readArticleSummary(response, event => {
                if (!current()) return;
                if (event.type === "token") display.append(event.content || event.data || "");
                else if (event.type === "status" && event.content) setStatus(event.content);
                else if (event.type === "sources") { refs = researchSources(event.sources); setSources(refs); }
                else if (event.type === "tool_step") {
                    const step = researchTool(event);
                    if (step) setSteps(rows => [...rows.filter(r => r.id !== step.id), step].sort((a, b) => a.id.localeCompare(b.id)));
                } else if (event.type === "research_evidence") {
                    const evidence = researchEvidence(event); setRecords(evidence.records); setCoverage(evidence.coverage);
                }
            }, "Pharma research");
            await display.finish();
            if (!current()) return;
            const completed = [...previous, { query, answer: text, sources: refs }];
            prior.current = completed; setTurns(completed); setAnswer(""); setQuestion("");
            const stored = saveResearchThread(completed, previous, id.current, owner.current); setSaved(stored);
        } catch (failure) {
            if (current()) { setAnswer(""); setError(failure instanceof Error ? failure.message : "Pharma research could not be completed."); }
        } finally {
            display.cancel(); if (reveal.current === display) reveal.current = null;
            if (abort.current === controller) { abort.current = null; setBusy(false); }
        }
    }, []);
    return { turns, answer, question, sources, steps, records, coverage, busy, status, error, saved,
        newResearch: () => {
            abort.current?.abort(); abort.current = null; reveal.current?.cancel(); id.current = crypto.randomUUID(); prior.current = []; pending.current = "";
            setTurns([]); setAnswer(""); setQuestion(""); setSources([]); setSteps([]); setRecords([]); setCoverage([]); setError(""); setSaved(false); setBusy(false);
        },
        ask: run, retry: () => run(pending.current), stop: () => { abort.current?.abort(); abort.current = null; reveal.current?.cancel(); setAnswer(""); setBusy(false); setError("Research stopped. No answer was saved for this question."); },
        showFull: () => reveal.current?.showAll() };
}
