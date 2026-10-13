export const PHARMA_TOPICS = [
  { id: "all", label: "All therapy areas" },
  { id: "oncology", label: "Oncology" },
  { id: "rare-disease", label: "Rare disease" },
  { id: "immunology", label: "Immunology" },
  { id: "cns", label: "Neuroscience" },
  { id: "cardiometabolic", label: "Cardiovascular & metabolic" },
] as const;
export type PharmaTopic = typeof PHARMA_TOPICS[number]["id"];
export type PharmaSourceId = "fda" | "trials" | "news" | "fda_updates" | "fda_safety" | "ema" | "company";
export const PHARMA_SOURCE_LABELS: Record<PharmaSourceId, string> = { fda: "FDA approvals", trials: "Trial events", news: "Trade news", fda_updates: "FDA announcements", fda_safety: "FDA safety", ema: "EMA decisions", company: "Company releases" };
export interface PharmaImpact { rating: "Material" | "Watch" | "None"; rationale: string; policy_version: string; basis: string; }
export interface PharmaItem {
  id: string; source: PharmaSourceId; title: string; summary: string;
  date: string; date_label: string; category: string; organization: string;
  url: string; tags: string[];
  thumbnail?: string;
  version?: string; document_id?: string; raw_version?: string;
  impact?: PharmaImpact;
  event?: { kind: string; label: string; date: string; date_label: string; baseline: boolean; reason: string | null; changes: unknown[] };
  drugs?: { id: string; name: string; evidence_url: string }[];
  details?: { application?: string; action?: string; ingredients?: string[]; study_id?: string; status?: string; phases?: string[]; conditions?: string[]; interventions?: string[] };
}
export interface PharmaSource {
  id: PharmaSourceId; name: string; url: string; cadence: string; scope: string;
  status: "available" | "empty" | "stale" | "unavailable" | "unconfigured" | "authentication_required";
  checked_at: string | null; source_updated_at: string | null;
  limited?: boolean; items: PharmaItem[];
  coverage?: { coverage?: string; method?: string };
}
export interface PharmaFeed {
  schema_version?: 2;
  topic: PharmaTopic; days: 7 | 30 | 90; since: string; until: string;
  checked_at: string; next_check_at: string; status: "available" | "stale" | "unavailable";
  partial: boolean; limit_per_source: number; items: PharmaItem[]; sources: PharmaSource[];
}
const SOURCES = Object.keys(PHARMA_SOURCE_LABELS);
const STATUSES = ["available", "empty", "stale", "unavailable", "unconfigured", "authentication_required"];
/** Only publisher-owned images; optional/malformed images never block records. */
export function pharmaThumbnail(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "i.guim.co.uk" && !url.username && !url.password && !url.port ? url.href : null;
  } catch { return null; }
}
/** Counts describe the loaded sample, with UTC date buckets and exclusive phase groups. */
export function pharmaOverview(feed: PharmaFeed) {
  const start = Date.parse(feed.since + "T00:00:00Z");
  const length = Math.floor((Date.parse(feed.until + "T00:00:00Z") - start) / 86400000) + 1;
  const bins = Array.from({ length: Math.min(7, length) }, (_, index) => ({
    date: new Date(start + Math.ceil(index * length / Math.min(7, length)) * 86400000).toISOString().slice(0, 10), fda: 0, trials: 0, news: 0,
  }));
  const phases = new Map<string, number>();
  for (const item of feed.items) {
    const day = Math.floor((Date.parse(item.date + "T00:00:00Z") - start) / 86400000);
    const group = item.source === "trials" ? "trials" : ["fda", "fda_updates", "fda_safety", "ema"].includes(item.source) ? "fda" : "news";
    if (day >= 0 && day < length) bins[Math.min(bins.length - 1, Math.floor(day * bins.length / length))][group]++;
    if (item.source === "trials") {
      const label = item.details?.phases?.length ? item.details.phases.map(p => p.replace(/^PHASE/, "Phase ").replaceAll("_", " ")).join(" / ") : "Not specified";
      phases.set(label, (phases.get(label) ?? 0) + 1);
    }
  }
  return { bins, phases: [...phases].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)),
    organizations: new Set(feed.items.map(i => i.organization.trim()).filter(Boolean)).size,
    trials: feed.items.filter(i => i.source === "trials").length };
}
function safeLink(value: unknown) {
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password;
  } catch { return false; }
}
function validDate(value: unknown): value is string {
  try { return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && new Date(value).toISOString().slice(0, 10) === value; }
  catch { return false; }
}
export function validPharmaItem(item: PharmaItem, since = "0001-01-01", until = "9999-12-31"): boolean {
  return !!item && typeof item === "object" && SOURCES.includes(item.source)
    && [item.id, item.title, item.summary, item.category, item.date_label, item.organization].every(v => typeof v === "string" && v.length <= 1200)
    && !!item.id && !!item.title && safeLink(item.url) && validDate(item.date) && item.date >= since && item.date <= until
    && Array.isArray(item.tags) && item.tags.length <= 12 && item.tags.every(v => typeof v === "string" && v.length <= 240)
    && (!item.version || /^[a-f0-9]{64}$/.test(item.version) && !!item.impact && ["Material", "Watch", "None"].includes(item.impact.rating)
      && typeof item.impact.rationale === "string" && item.impact.rationale.length <= 1200
      && !!item.event && typeof item.event.kind === "string" && typeof item.event.label === "string" && item.event.label.length <= 240
      && validDate(item.event.date) && item.event.date === item.date && typeof item.event.baseline === "boolean" && Array.isArray(item.event.changes)
      && Array.isArray(item.drugs) && item.drugs.length <= 8 && item.drugs.every(d => /^[a-f0-9]{64}$/.test(d.id) && typeof d.name === "string" && safeLink(d.evidence_url)))
    && (!item.details || typeof item.details === "object" && !Array.isArray(item.details) && Object.values(item.details).every(v => typeof v === "string" || Array.isArray(v) && v.length <= 12 && v.every(s => typeof s === "string" && s.length <= 240)));
}
export function parsePharmaFeed(value: unknown, topic: PharmaTopic, days: number): PharmaFeed {
  const feed = value as PharmaFeed;
  const count = feed?.schema_version === 2 ? 7 : 3;
  if (!feed || feed.topic !== topic || feed.days !== days || !validDate(feed.since) || !validDate(feed.until)
    || feed.since > feed.until || !Number.isFinite(Date.parse(feed.checked_at)) || !Number.isFinite(Date.parse(feed.next_check_at))
    || !["available", "stale"].includes(feed.status) || typeof feed.partial !== "boolean" || feed.limit_per_source !== 20
    || !Array.isArray(feed.items) || feed.items.length > count * 20 || !feed.items.every(i => validPharmaItem(i, feed.since, feed.until))
    || new Set(feed.items.map(i => i.id)).size !== feed.items.length
    || !Array.isArray(feed.sources) || feed.sources.length !== count || !feed.sources.every(s => !!s && typeof s === "object") || new Set(feed.sources.map(s => s.id)).size !== count
    || !feed.sources.every(s => SOURCES.includes(s.id) && STATUSES.includes(s.status) && safeLink(s.url)
      && [s.name, s.cadence, s.scope].every(v => typeof v === "string") && Array.isArray(s.items) && s.items.length <= 20
      && s.items.every(i => i.source === s.id && validPharmaItem(i, feed.since, feed.until))
      && (s.checked_at === null || Number.isFinite(Date.parse(s.checked_at)))
      && (s.source_updated_at === null || validDate(s.source_updated_at)))) {
    throw new Error("The pharma feed returned an invalid response. Please retry.");
  }
  const sourceItems = feed.sources.flatMap(s => s.items).map(i => i.id).sort();
  if (JSON.stringify(sourceItems) !== JSON.stringify(feed.items.map(i => i.id).sort())) throw new Error("The pharma feed returned inconsistent records. Please retry.");
  return feed;
}
/** Retention never renews source timestamps or presents an outage as freshness. */
export function retainPharmaFeed(feed: PharmaFeed, now = Date.now()): PharmaFeed | null {
  const sources = feed.sources.map(source => {
    const age = source.checked_at ? now - Date.parse(source.checked_at) : Infinity;
    if (["available", "empty", "stale"].includes(source.status)) {
      return age >= 0 && age <= 24 * 3600_000 ? { ...source, status: "stale" as const } : { ...source, status: "unavailable" as const, items: [], checked_at: null };
    }
    return source;
  });
  const items = sources.flatMap(s => s.items).sort((a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id));
  if (!sources.some(s => s.status === "stale")) return null;
  return { ...feed, status: "stale", partial: true, sources, items, next_check_at: new Date(now + 60_000).toISOString() };
}
export class PharmaRequestError extends Error {
  constructor(public retryable: boolean, public retryAfterMs = 0) { super("Pharma updates are temporarily unavailable. Please retry shortly."); }
}
function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const cancel = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", cancel); resolve(); }, ms);
    if (signal.aborted) cancel(); else signal.addEventListener("abort", cancel, { once: true });
  });
}
/** Only read-only GETs are retried. Bound the deadline and honor Retry-After. */
export async function requestPharmaFeed(topic: PharmaTopic, days: 7 | 30 | 90, signal: AbortSignal, onWait?: () => void,
  options: { fetcher?: typeof fetch; budgetMs?: number; attemptMs?: number } = {}): Promise<PharmaFeed> {
  const deadline = Date.now() + (options.budgetMs ?? 90_000);
  for (let attempt = 0; attempt < 7; attempt++) {
    signal.throwIfAborted();
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    try {
      const response = await (options.fetcher ?? fetch)(`/api/v1/pharma/updates?topic=${topic}&days=${days}`, {
        cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(Math.max(1, Math.min(remaining, options.attemptMs ?? 18_000)))]),
      });
      if (!response.ok) {
        const retry = response.headers.get("Retry-After");
        const seconds = retry && /^\d+(\.\d+)?$/.test(retry) ? Number(retry) : retry ? Math.max(0, (Date.parse(retry) - Date.now()) / 1000) : 0;
        throw new PharmaRequestError([408, 429, 500, 502, 503, 504].includes(response.status), Number.isFinite(seconds) ? seconds * 1000 : 0);
      }
      let data: unknown;
      try { data = await response.json(); } catch { throw new PharmaRequestError(true); }
      return parsePharmaFeed(data, topic, days);
    } catch (error) {
      signal.throwIfAborted();
      if (!(error instanceof PharmaRequestError) && !(error instanceof TypeError) && !(error instanceof DOMException)) throw error;
      if (error instanceof PharmaRequestError && !error.retryable) throw error;
      const wait = Math.max(1500 * (attempt + 1), error instanceof PharmaRequestError ? error.retryAfterMs : 0);
      if (attempt === 6 || wait >= deadline - Date.now()) throw new PharmaRequestError(false);
      onWait?.();
      await pause(wait, signal);
    }
  }
  throw new PharmaRequestError(false);
}
export function filterPharmaItems(items: PharmaItem[], source: string, query: string) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item => (source === "all" || item.source === source)
    && words.every(word => [item.title, item.summary, item.organization, ...item.tags, ...Object.values(item.details ?? {}).flat()].join(" ").toLocaleLowerCase().includes(word)));
}
export function pharmaCsv(items: PharmaItem[], feed: PharmaFeed) {
  // Spreadsheet formula neutralization applies to source-controlled text, too.
  const cell = (value: string) => `"${(/^[\s]*[=+\-@\t\r]/.test(value) ? "'" + value : value).replaceAll('"', '""')}"`;
  const rows = [["Source", "Record type", "Title", "Organization", "Event date", "Date meaning", "Summary", "URL", "Source checked at", "Source status", "Therapy filter", "Coverage", "Window start", "Window end", "Record ID", "Study or application ID", "Trial phases", "Study status", "Interventions or ingredients", "Event", "Impact", "Impact basis", "Reported stop reason", "Verified drug identities", "Source version"],
    ...items.map(i => { const source = feed.sources.find(s => s.id === i.source)!; return [source.name, i.category, i.title, i.organization, i.date, i.date_label, i.summary, i.url, source.checked_at ?? "", source.status, i.source === "fda" ? "all" : feed.topic, source.scope, feed.since, feed.until, i.id, i.details?.study_id ?? i.details?.application ?? "", i.details?.phases?.join("; ") ?? "", i.details?.status ?? "", (i.details?.interventions ?? i.details?.ingredients ?? []).join("; "), i.event?.label ?? "", i.impact?.rating ?? "", i.impact?.rationale ?? "", i.event?.reason ?? "", i.drugs?.map(d => d.name).join("; ") ?? "", i.version ?? ""]; })];
  return "\uFEFF" + rows.map(row => row.map(cell).join(",")).join("\r\n") + "\r\n";
}
