import { api } from "./api";
import { conversationMessages } from "./conversation";
import { accountStorage, getStorageAccount } from "./accountStorage";
import { isPrivateChat } from "./questionDrafts";
import type { PharmaTurn } from "./pharmaRecord";
import type { SearchSource, ThreadData } from "@/hooks/useSearch";

export interface PharmaToolStep { id: string; label: string; status: "running" | "available" | "empty" | "unavailable"; count?: number; }
export interface PharmaEvidence { citation: number; title: string; url: string; kind: string; facts: Record<string, unknown>; excerpt: string; date?: string | null; date_meaning?: string | null; retrieved_at: string; }
export interface PharmaCoverage { tool: string; status: string; coverage: string; }
export type PharmaResearchThread = ThreadData & { pharmaResearch: { version: 1 } };

export function researchMessages(turns: PharmaTurn[]) {
    const messages = conversationMessages(turns).slice(-12), encoder = new TextEncoder();
    let size = 0;
    const selected = [];
    for (const message of messages.toReversed()) {
        const length = encoder.encode(message.content).length;
        if (size + length > 12000) break;
        selected.unshift(message); size += length;
    }
    return selected;
}

export function openPharmaResearch(query: string, turns: PharmaTurn[], signal: AbortSignal, record?: { record_id: string; record_fingerprint: string }) {
    return api.response("/api/v1/pharma/research/stream", { method: "POST", signal,
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ query, messages: researchMessages(turns), ...record }) });
}

function publicUrl(value: unknown): value is string {
    if (typeof value !== "string" || value.length > 2048) return false;
    try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password; } catch { return false; }
}
export function researchSources(value: unknown): SearchSource[] {
    if (!Array.isArray(value)) return [];
    return value.slice(0, 20).filter((s): s is SearchSource => !!s && publicUrl(s.url) && typeof s.title === "string" && typeof s.domain === "string" && Number.isInteger(s.citationIndex) && s.citationIndex > 0 && s.citationIndex <= 20);
}
export function researchTool(value: unknown): PharmaToolStep | null {
    if (!value || typeof value !== "object") return null;
    const v = value as PharmaToolStep;
    return typeof v.id === "string" && v.id.length < 20 && typeof v.label === "string" && v.label.length < 200 && ["running", "available", "empty", "unavailable"].includes(v.status)
        ? { id: v.id, label: v.label, status: v.status, count: Number.isInteger(v.count) && v.count! >= 0 ? v.count : undefined } : null;
}
export function researchEvidence(value: unknown): { records: PharmaEvidence[]; coverage: PharmaCoverage[] } {
    if (!value || typeof value !== "object") return { records: [], coverage: [] };
    const v = value as { records?: unknown[]; coverage?: unknown[] };
    return {
        records: Array.isArray(v.records) ? v.records.slice(0, 24).filter((r): r is PharmaEvidence => {
            const e = r as PharmaEvidence;
            return !!e && Number.isInteger(e.citation) && e.citation > 0 && e.citation <= 20 && publicUrl(e.url) && typeof e.title === "string" && typeof e.kind === "string" && typeof e.excerpt === "string" && typeof e.retrieved_at === "string" && !!e.facts && typeof e.facts === "object" && !Array.isArray(e.facts);
        }) : [],
        coverage: Array.isArray(v.coverage) ? v.coverage.slice(0, 4).filter((r): r is PharmaCoverage => {
            const e = r as PharmaCoverage; return !!e && typeof e.tool === "string" && typeof e.status === "string" && typeof e.coverage === "string";
        }) : [],
    };
}

export function evidenceCsv(rows: PharmaEvidence[], coverage: PharmaCoverage[]) {
    const cell = (value: unknown) => {
        let text = typeof value === "string" ? value : JSON.stringify(value ?? "");
        if (/^[\s]*[=+\-@\t\r]/.test(text)) text = "'" + text; // Spreadsheet formula injection.
        return '"' + text.replace(/"/g, '""') + '"';
    };
    const data: unknown[][] = [["Type", "Reference", "Title", "URL", "Date", "Date meaning", "Retrieved UTC", "Facts", "Excerpt / coverage"]];
    rows.forEach(r => data.push([r.kind, r.citation, r.title, r.url, r.date, r.date_meaning, r.retrieved_at, r.facts, r.excerpt]));
    coverage.forEach(c => data.push(["coverage", "", c.tool, "", "", "", "", c.status, c.coverage]));
    return "\ufeff" + data.map(row => row.map(cell).join(",")).join("\r\n");
}
export function researchReport(query: string, answer: string, sources: SearchSource[], coverage: PharmaCoverage[]) {
    return `# Pharma research\n\n${query}\n\n${answer}\n\n## References\n\n` + sources.map(s => `[${s.citationIndex}] ${s.title}\n${s.url}`).join("\n\n")
        + "\n\n## Coverage\n\n" + coverage.map(c => `- ${c.tool} (${c.status}): ${c.coverage}`).join("\n") + "\n";
}

export function pharmaThreadPath(thread: { id: string; pharmaResearch?: { version?: number }; pharmaRecord?: { id?: string } }) {
    if (thread.pharmaRecord?.id) return `/analyst-workspace/pharma/${encodeURIComponent(thread.pharmaRecord.id)}`;
    return `${thread.pharmaResearch?.version === 1 ? "/analyst-workspace/pharma/research" : "/search"}?id=${encodeURIComponent(thread.id)}`;
}
export function restoreResearchThread(id: string): PharmaResearchThread | null {
    if (!id || isPrivateChat()) return null;
    try {
        const rows = JSON.parse(accountStorage.getItem("corten_threads") || "[]");
        const thread = Array.isArray(rows) ? rows.find(t => t?.id === id && t.pharmaResearch?.version === 1) : null;
        if (!thread || !Array.isArray(thread.history) || ![...thread.history, thread].every(t => typeof t.query === "string" && typeof t.answer === "string" && t.answer.trim() && Array.isArray(t.sources))) return null;
        return thread;
    } catch { return null; }
}
export function saveResearchThread(turns: PharmaTurn[], previous: PharmaTurn[], id: string, owner: string | null) {
    if (!turns.length || !owner || owner !== getStorageAccount() || isPrivateChat()) return false;
    try {
        const rows = JSON.parse(accountStorage.getItem("corten_threads") || "[]") as ThreadData[];
        if (!Array.isArray(rows)) return false;
        const prior = rows.find(t => t.id === id);
        const body = (ts: { query: string; answer: string }[]) => JSON.stringify(ts.map(t => [t.query, t.answer]));
        if ((!prior && previous.length) || (prior && body([...prior.history, prior]) !== body(previous))) return false;
        const now = Date.now(), last = turns.at(-1)!;
        const thread: PharmaResearchThread = { ...prior, id, title: prior?.title || turns[0].query.slice(0, 100), createdAt: prior?.createdAt || now, updatedAt: now,
            ...last, history: turns.slice(0, -1).map(t => ({ ...t, images: [] })), images: [], pharmaResearch: { version: 1 } };
        if (new TextEncoder().encode(JSON.stringify(thread)).length > 240000) return false;
        accountStorage.setItem("corten_threads", JSON.stringify([thread, ...rows.filter(t => t.id !== id)]));
        window.dispatchEvent(new Event("corten_threads_updated")); return true;
    } catch { return false; }
}
