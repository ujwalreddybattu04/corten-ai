import { api } from './api';
import { isPrivateChat } from './questionDrafts';
import { getStorageAccount } from './accountStorage';

export const DEEP_TYPES = {
    drug_profile: 'Drug profile', head_to_head: 'Head-to-head comparison', landscape: 'Competitive landscape',
    generic_entry: 'Generic entry', safety: 'Safety review', company_pipeline: 'Company pipeline',
} as const;
export type DeepType = keyof typeof DEEP_TYPES;
export type DeepTopic = 'approvals' | 'trials' | 'labels' | 'patents' | 'recalls' | 'ema' | 'literature' | 'company' | 'sec';
export interface DeepPlan { question_type: DeepType; subjects: string[]; topics: DeepTopic[]; condition: string | null; max_rounds: number; phase?: 'PHASE1' | 'PHASE2' | 'PHASE3' | 'PHASE4' | null; }
export interface DeepOptions { topics: { id: DeepTopic; label: string; description: string }[]; checklists: Record<DeepType, DeepTopic[]>; limits: { rounds: number; documents: number; lookups: number; reports_per_day: number }; }
export interface DeepSource { id: number; title: string; url: string; date?: string | null; date_meaning?: string | null; retrieved_at: string; read_status: string; topics: DeepTopic[]; }
export interface DeepQuote { id: string; source: number; topic: DeepTopic; text: string; method: string; field?: string | null; }
export interface DeepCoverage { topic: DeepTopic; label: string; status: string; sources: number; quotes: number; detail: string; }
export interface DeepActivity { id: number; stage: string; title: string; detail: string; status: string; round: number; at: string; task?: string | null; }
export interface DeepReport { version: number; title: string; query: string; generated_at: string; markdown: string; sources: DeepSource[]; quotes: DeepQuote[]; coverage: DeepCoverage[]; metrics: Record<string, number>; sample_notice: string; search_coverage?: { topic: DeepTopic; query: string; status: string; coverage: string }[]; }
export interface DeepJob { id: string; query: string; status: string; stage: string; plan: DeepPlan; revision: number; created_at: string; started_at: string | null; completed_at: string | null; activity: DeepActivity[]; report?: DeepReport | null; metrics?: Record<string, number>; coverage?: DeepCoverage[]; evidence_preview?: DeepQuote[]; outline?: { heading: string; topics: DeepTopic[] }[]; error?: string; retryable?: boolean; }
export const DEEP_STAGES = [{ id: 'plan', label: 'Plan' }, { id: 'search', label: 'Search' }, { id: 'read', label: 'Read' }, { id: 'gaps', label: 'Check gaps' }, { id: 'write', label: 'Write' }, { id: 'verify', label: 'Verify' }, { id: 'deliver', label: 'Deliver' }];
export const deepActive = (job: DeepJob | null) => !!job && ['queued', 'running', 'cancel_requested'].includes(job.status);
export const deepSourceMethod = (method: string) => ({ api_record: 'Structured API record', api_section: 'API section passage', document_passage: 'Document passage', abstract_page: 'Abstract page read', abstract_passage: 'Abstract passage', search_excerpt: 'Search excerpt', document_read: 'Document read', bounded_document: 'Document read · limited' }[method] || method.replaceAll('_', ' '));
export function deepSources(sources: DeepSource[]) {
    return sources.flatMap(source => {
        try {
            const url = new URL(source.url);
            return url.protocol === 'https:' && !url.username && !url.password && Number.isInteger(source.id) && source.id > 0 && source.id <= 40
                ? [{ title: source.title, url: source.url, domain: url.hostname, citationIndex: source.id }] : [];
        } catch { return []; }
    });
}
export function checkDeepJob(value: unknown): DeepJob {
    const job = value as DeepJob;
    if (!job || !/^[a-f0-9-]{36}$/i.test(job.id) || typeof job.query !== 'string' || !job.plan || !Array.isArray(job.plan.topics) || !Array.isArray(job.activity) || !Number.isInteger(job.revision)) throw new Error('The research response could not be read. Please reload.');
    return job;
}
export async function prepareDeep(query: string, signal?: AbortSignal, allowSaved = false) { return checkDeepJob(await api.post('/api/v1/pharma/deep/plan', { query, private: isPrivateChat() && !allowSaved }, { signal })); }
export async function readDeep(id: string, signal?: AbortSignal) { return checkDeepJob(await api.get(`/api/v1/pharma/deep/${encodeURIComponent(id)}`, { signal })); }
export async function startDeep(job: DeepJob, plan: DeepPlan) { return checkDeepJob(await api.post(`/api/v1/pharma/deep/${job.id}/start`, { plan, revision: job.revision, private: false })); }
export async function actDeep(job: DeepJob, action: 'cancel' | 'retry') { return checkDeepJob(await api.post(`/api/v1/pharma/deep/${job.id}/${action}`)); }
const draftKey = () => `corten_deep_draft:${getStorageAccount() || 'guest'}`;
export function rememberDeepDraft(query: string) { try { sessionStorage.setItem(draftKey(), query.slice(0, 4000)); } catch { /* The new research page remains available. */ } }
export function takeDeepDraft(): string { try { const key = draftKey(), query = sessionStorage.getItem(key) || ''; sessionStorage.removeItem(key); return query.slice(0, 4000); } catch { return ''; } }
