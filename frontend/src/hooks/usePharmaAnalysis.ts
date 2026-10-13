"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getStorageAccount } from "@/lib/accountStorage";
import { getAnswerMode } from "@/lib/chatApi";
import { isPrivateChat } from "@/lib/questionDrafts";
import { conversationMessages } from "@/lib/conversation";
import { openSearchStream } from "@/lib/searchConnection";
import { readArticleSummary } from "@/lib/articleSummaryStream";
import { PHARMA_ANALYSIS_PROMPT, PHARMA_REFRESH_LABEL, currentPharmaTurns, pharmaDisplayQuery, pharmaFingerprint, pharmaOriginalSource, restorePharmaThread, savePharmaThread, type PharmaRecord, type PharmaTurn } from "@/lib/pharmaRecord";
import type { ResearchStep, SearchSource } from "@/hooks/useSearch";

export function usePharmaAnalysis(record: PharmaRecord) {
    const [turns, setTurns] = useState<PharmaTurn[]>([]);
    const [answer, setAnswer] = useState("");
    const [question, setQuestion] = useState("");
    const [sources, setSources] = useState<SearchSource[]>([]);
    const [steps, setSteps] = useState<ResearchStep[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [saved, setSaved] = useState(false);
    const [related, setRelated] = useState<string[]>([]);
    const [model, setModel] = useState("");
    const controller = useRef<AbortController | null>(null);
    const turnsRef = useRef<PharmaTurn[]>([]);
    const id = useRef("");
    const owner = useRef(getStorageAccount());
    const pending = useRef<{ query: string; label?: string } | null>(null);
    const run = useCallback(async (query: string, label?: string) => {
        if (controller.current || !query.trim() || query.length > 16000) return;
        const abort = new AbortController(); controller.current = abort; pending.current = { query, label };
        const initial = !turnsRef.current.length;
        const display = label || (initial ? pharmaDisplayQuery(record) : query);
        const previous = [...turnsRef.current];
        let canonicalSources = [pharmaOriginalSource(record)], text = "";
        setBusy(true); setError(""); setAnswer(""); setQuestion(display); setSources(canonicalSources); setSteps([]); setRelated([]);
        const current = () => !abort.signal.aborted && controller.current === abort && getStorageAccount() === owner.current;
        try {
            const response = await openSearchStream({ apiBase: "", query, focus: "all", mode: getAnswerMode(), incognito: isPrivateChat(),
                pharma: { record_id: record.item.id, record_fingerprint: pharmaFingerprint(record), topic: record.feed.topic,
                    days: record.feed.days, kind: query === PHARMA_ANALYSIS_PROMPT ? "brief" : "question" },
                messages: query === PHARMA_ANALYSIS_PROMPT ? [] : conversationMessages(currentPharmaTurns(previous)).slice(-120) }, abort.signal,
                message => { if (current()) setSteps([{ type: "status", content: message }]); });
            text = await readArticleSummary(response, event => {
                if (!current()) return;
                if (event.type === "token") setAnswer(value => value + (event.content || event.data || ""));
                else if (event.type === "sources" && (event.sources || event.items)) {
                    const next = (event.sources || event.items) as SearchSource[];
                    if (next.length) { canonicalSources = next; setSources(next); }
                } else if (["status", "thought", "query_step"].includes(event.type) && event.content) {
                    setSteps(value => [...value, { type: event.type as ResearchStep["type"], content: event.content! }]);
                } else if (event.type === "related") {
                    const questions = (event as unknown as { questions?: unknown }).questions;
                    if (Array.isArray(questions)) setRelated(questions.filter((q): q is string => typeof q === "string").slice(0, 5));
                } else if (event.type === "analysis_meta" && query === PHARMA_ANALYSIS_PROMPT) {
                    const metadata = event as unknown as { model?: unknown; basis?: unknown };
                    if (typeof metadata.model === "string") setModel(metadata.basis === "source_summary" ? "Source-based summary" : metadata.model === "amazon.nova-pro-v1:0" ? "Amazon Nova Pro · AWS Bedrock" : metadata.model === "amazon.nova-lite-v1:0" ? "Amazon Nova Lite · AWS Bedrock" : "");
                }
            }, "analysis");
            if (!current()) return;
            const completed = [...previous, { query: display, answer: text, sources: canonicalSources }].slice(-60);
            turnsRef.current = completed; setTurns(completed); setAnswer(""); setQuestion("");
            setSaved(savePharmaThread(record, completed, previous, id.current, owner.current));
        } catch (failure) {
            if (current()) { setAnswer(""); setError(failure instanceof Error ? failure.message : "The analysis could not be completed. Please retry."); }
        } finally { if (controller.current === abort) { controller.current = null; setBusy(false); } }
    }, [record]);
    useEffect(() => {
        // Cleanup cancels this timer before React's development remount can issue a POST.
        const timer = setTimeout(() => {
            owner.current = getStorageAccount();
            const prior = restorePharmaThread(record);
            id.current = prior?.id || crypto.randomUUID();
            if (prior) {
                const restored = [...prior.history, prior].map(t => ({ query: t.query, answer: t.answer, sources: t.sources }));
                turnsRef.current = restored; setTurns(restored); setSaved(true);
            } else void run(PHARMA_ANALYSIS_PROMPT);
        }, 50);
        return () => { clearTimeout(timer); controller.current?.abort(); controller.current = null; };
    }, [record, run]);
    return { turns: busy && pending.current?.query === PHARMA_ANALYSIS_PROMPT ? [] : currentPharmaTurns(turns),
        answer, question, sources, steps, busy, error, saved, related, model, threadId: saved ? id.current : "",
        ask: run, refresh: () => run(PHARMA_ANALYSIS_PROMPT, PHARMA_REFRESH_LABEL),
        retry: () => run(pending.current?.query || PHARMA_ANALYSIS_PROMPT, pending.current?.label) };
}
