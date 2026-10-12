import { api, ApiRequestError } from "./api";
import { accountStorage, getStorageAccount, observeAccountWrites } from "./accountStorage";

type Namespace = "threads" | "spaces" | "preferences";
interface CloudRecord { namespace: Namespace; id: string; revision: number; deleted: boolean; data: unknown; }
interface Pending extends Omit<CloudRecord, "revision"> { expected_revision: number; }
interface Response { records: CloudRecord[]; cursor: number; has_more: boolean; }
type Outcome = CloudRecord & { status: "saved" | "conflict" | "quota"; current?: CloudRecord | null; reason?: string };
export type SyncStatus = "guest" | "loading" | "saved" | "pending" | "offline" | "conflict";
let current: { owner: string; stop: () => void; refresh: () => Promise<void> } | null = null;
let status: SyncStatus = "guest";
let syncError = "";
export const getCloudSyncStatus = () => status;
export const getCloudSyncError = () => syncError;
function report(value: SyncStatus, message = "") { status = value; syncError = message; window.dispatchEvent(new Event("corten_sync_status")); }
const ARRAY_KEYS: Record<string, Namespace> = { corten_threads: "threads", corten_spaces: "spaces" };
const PREFERENCES = new Set(["corten_pinned_threads", "corten_answer_feedback", "discover_interactions_v2", "discover_affinities_v3", "discover_disliked_v2", "discover_liked_v2", "discover_bookmarked_v2", "discover_interests"]);
const STORE_KEYS: Record<Namespace, string> = { threads: "corten_threads", spaces: "corten_spaces", preferences: "" };
export function cloudRecords(name: string, raw: string | null): Map<string, unknown> {
    const result = new Map<string, unknown>();
    if (!ARRAY_KEYS[name] && !PREFERENCES.has(name)) return result;
    let value: unknown;
    try { value = raw === null ? null : JSON.parse(raw); } catch { return result; }
    if (ARRAY_KEYS[name]) {
        if (Array.isArray(value)) for (const item of value) if (item && typeof item === "object" && typeof item.id === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(item.id)) result.set(item.id, item);
    } else if (raw !== null) result.set(name, value);
    return result;
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** A conflicting edit is preserved as a separate copy; a remote deletion is never undone. */
export function conflictCopy(record: Pending, remote: CloudRecord | null): Pending | null {
    if (record.deleted || record.namespace === "preferences" || record.data === null || typeof record.data !== "object" || Array.isArray(record.data)) return null;
    if (remote && !remote.deleted && same(remote.data, record.data)) return null;
    const id = crypto.randomUUID();
    const data = { ...record.data, id, updatedAt: Date.now() } as Record<string, unknown>;
    const label = record.namespace === "threads" ? "title" : "name";
    data[label] = `${typeof data[label] === "string" ? data[label] : "Saved record"} (conflict copy)`;
    return { ...record, id, expected_revision: 0, data };
}

export function stopCloudSync() { current?.stop(); current = null; report("guest"); }
export async function refreshCloudSync() { await current?.refresh(); }
export async function startCloudSync(owner: string): Promise<void> {
    if (current?.owner === owner) return;
    stopCloudSync();
    report("loading");
    let stopped = false, busy = false, cursor = 0, applying = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const revisions = new Map<string, number>();
    const pending = new Map<string, Pending>();
    const draftKey = "corten_cloud_pending";
    const revisionKey = "corten_cloud_revisions";
    const controller = new AbortController();
    const identity = (namespace: string, id: string) => namespace + ":" + id;
    const valid = () => !stopped && owner === getStorageAccount();
    const privateMode = () => sessionStorage.getItem("corten_private_mode") === "true";
    const persist = () => { if (valid()) { accountStorage.setItem(draftKey, JSON.stringify([...pending.values()])); accountStorage.setItem(revisionKey, JSON.stringify([...revisions])); } };
    try {
        const saved = JSON.parse(accountStorage.getItem(revisionKey) || "[]");
        if (Array.isArray(saved)) for (const pair of saved) if (Array.isArray(pair) && typeof pair[0] === "string" && Number.isSafeInteger(pair[1]) && pair[1] >= 0) revisions.set(pair[0], pair[1]);
    } catch { /* An invalid cursor never grants ownership. */ }
    try {
        const drafts = JSON.parse(accountStorage.getItem(draftKey) || "[]");
        if (Array.isArray(drafts)) for (const item of drafts) if (item && ["threads", "spaces", "preferences"].includes(item.namespace) && typeof item.id === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(item.id) && Number.isSafeInteger(item.expected_revision) && item.expected_revision >= 0 && typeof item.deleted === "boolean") pending.set(identity(item.namespace, item.id), item);
    } catch { /* Keep account data even if a draft queue is corrupt. */ }
    const merge = (record: CloudRecord, force = false) => {
        if (!valid()) return;
        const key = identity(record.namespace, record.id);
        if ((revisions.get(key) ?? 0) > record.revision) return;
        revisions.set(key, record.revision);
        if (pending.has(key) && !force) return;
        applying = true;
        try {
            if (record.namespace === "preferences") {
                if (!PREFERENCES.has(record.id)) return;
                if (record.deleted) accountStorage.removeItem(record.id); else accountStorage.setItem(record.id, JSON.stringify(record.data));
            } else if (STORE_KEYS[record.namespace]) {
                const name = STORE_KEYS[record.namespace];
                const rows = [...cloudRecords(name, accountStorage.getItem(name)).values()] as Array<{ id: string; updatedAt?: number }>;
                const remaining = rows.filter(item => item.id !== record.id);
                if (!record.deleted && record.data && typeof record.data === "object") remaining.push(record.data as { id: string });
                remaining.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
                accountStorage.setItem(name, JSON.stringify(remaining));
            }
        } finally { applying = false; }
        window.dispatchEvent(new Event(record.namespace === "threads" ? "corten_threads_updated" : record.namespace === "spaces" ? "corten_spaces_updated" : "corten_preferences_updated"));
    };
    const pull = async () => {
        const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]);
        for (let page = 0; page < 110; page++) {
            let response: Response;
            try { response = await api.get<Response>(`/api/v1/personal/changes?after=${cursor}&limit=50`, { signal }); }
            catch (error) { if (error instanceof ApiRequestError && error.status === 409 && cursor > 0) { cursor = 0; continue; } throw error; }
            if (!valid()) return;
            if (!Array.isArray(response.records) || !Number.isSafeInteger(response.cursor) || response.cursor < cursor || typeof response.has_more !== "boolean") throw new Error("Invalid cloud response");
            for (const record of response.records) {
                if (!record || !["threads", "spaces", "preferences", "collections"].includes(record.namespace) || typeof record.id !== "string" || !Number.isSafeInteger(record.revision) || typeof record.deleted !== "boolean") throw new Error("Invalid cloud record");
                if (record.namespace !== ("collections" as string)) merge(record);
            }
            if (response.has_more && response.cursor === cursor) throw new Error("Cloud pagination did not advance");
            cursor = response.cursor;
            if (!response.has_more) return;
        }
        throw new Error("Cloud pagination limit reached");
    };
    const flush = async () => {
        if (!valid() || privateMode()) return;
        // One bounded batch per pass; additional edits remain queued durably.
        const batch: Pending[] = []; let bytes = 0;
        for (const entry of pending.values()) {
            const size = new TextEncoder().encode(JSON.stringify(entry)).byteLength;
            if (batch.length && (batch.length >= 16 || bytes + size > 500000)) break;
            bytes += size; batch.push(entry);
        }
        if (!batch.length) return;
        const response = await api.post<{ results: Outcome[] }>("/api/v1/personal/records", { records: batch }, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]) });
        if (!valid()) return;
        if (!Array.isArray(response.results) || response.results.length !== batch.length) throw new Error("Invalid cloud write response");
        let conflicted = false;
        for (let index = 0; index < batch.length; index++) {
            const sent = batch[index], result = response.results[index];
            const key = identity(sent.namespace, sent.id);
            if (result.namespace !== sent.namespace || result.id !== sent.id) throw new Error("Cloud write identity mismatch");
            const newer = pending.get(key);
            if (result.status === "saved") {
                if (!Number.isSafeInteger(result.revision)) throw new Error("Invalid cloud revision");
                revisions.set(key, result.revision);
                if (same(newer, sent)) pending.delete(key);
                else if (newer) pending.set(key, { ...newer, expected_revision: result.revision });
            } else if (result.status === "conflict") {
                pending.delete(key);
                if (result.current) merge(result.current);
                const copy = conflictCopy(newer || sent, result.current || null);
                if (copy) { merge({ ...copy, revision: 0 }, true); pending.set(identity(copy.namespace, copy.id), copy); }
                conflicted = true;
            } else throw new ApiRequestError(result.reason === "retained_history" ? "Retained change history is full. Your local work is preserved; contact support before retrying." : "Cloud storage limit reached. Export or remove older records before retrying.", 413);
        }
        persist();
        if (conflicted) report("conflict");
    };
    const schedule = (delay = 700) => { clearTimeout(timer); timer = setTimeout(() => void refresh(), delay); };
    const observe = (name: string, before: string | null, after: string | null) => {
        if (!valid() || applying || privateMode() || (!ARRAY_KEYS[name] && !PREFERENCES.has(name))) return;
        if (after !== null) { try { JSON.parse(after); } catch { report("offline"); return; } }
        const namespace = ARRAY_KEYS[name] || "preferences";
        const prior = cloudRecords(name, before), next = cloudRecords(name, after);
        for (const id of new Set([...prior.keys(), ...next.keys()])) {
            if (same(prior.get(id), next.get(id))) continue;
            const key = identity(namespace, id);
            const expected = pending.get(key)?.expected_revision ?? revisions.get(key) ?? 0;
            pending.set(key, { namespace, id, expected_revision: expected, deleted: !next.has(id), data: next.get(id) ?? null });
        }
        persist(); report("pending"); schedule();
    };
    const unsubscribe = observeAccountWrites(observe);
    const storage = (event: StorageEvent) => {
        const prefix = `corten_account:${owner}:`;
        if (event.key?.startsWith(prefix)) {
            const name = event.key.slice(prefix.length);
            if (name === draftKey) {
                try { for (const item of JSON.parse(event.newValue || "[]")) if (item && typeof item.id === "string" && Number.isSafeInteger(item.expected_revision)) pending.set(identity(item.namespace, item.id), item); } catch { /* Retain this tab's pending changes. */ }
                schedule();
            } else if (name === revisionKey) {
                try { for (const [key, value] of JSON.parse(event.newValue || "[]")) if (typeof key === "string" && Number.isSafeInteger(value)) revisions.set(key, Math.max(value, revisions.get(key) || 0)); } catch { /* Pull will recover valid metadata. */ }
            } else {
                // Another tab's cache is already updated. Its durable queue owns the write.
                window.dispatchEvent(new Event(ARRAY_KEYS[name] === "threads" ? "corten_threads_updated" : ARRAY_KEYS[name] === "spaces" ? "corten_spaces_updated" : "corten_preferences_updated"));
                schedule();
            }
        }
    };
    const refresh = async () => {
        if (!valid() || busy || document.visibilityState === "hidden") return;
        busy = true;
        try {
            await pull();
            await flush();
            if (valid() && status !== "conflict") report(pending.size ? "pending" : "saved");
        } catch (error) { if (valid()) report("offline", error instanceof ApiRequestError && error.status < 500 ? error.message : ""); }
        finally { busy = false; if (valid()) schedule(pending.size && status !== "offline" ? 1000 : 60000); }
    };
    const wake = () => { if (document.visibilityState !== "hidden") void refresh(); };
    window.addEventListener("online", wake); window.addEventListener("focus", wake); window.addEventListener("storage", storage); document.addEventListener("visibilitychange", wake);
    current = { owner, refresh, stop: () => { stopped = true; controller.abort(); clearTimeout(timer); unsubscribe(); window.removeEventListener("online", wake); window.removeEventListener("focus", wake); window.removeEventListener("storage", storage); document.removeEventListener("visibilitychange", wake); } };
    // Import only this authenticated account's pre-existing browser records.
    const local = new Map<string, { namespace: Namespace; id: string; data: unknown }>();
    for (const name of [...Object.keys(ARRAY_KEYS), ...PREFERENCES]) for (const [id, data] of cloudRecords(name, accountStorage.getItem(name))) local.set(identity(ARRAY_KEYS[name] || "preferences", id), { namespace: ARRAY_KEYS[name] || "preferences", id, data });
    if (!privateMode()) for (const [key, item] of local) if (!revisions.has(key) && !pending.has(key)) pending.set(key, { ...item, expected_revision: 0, deleted: false });
    persist();
    busy = true;
    try {
        await pull();
        if (!valid()) return;
        persist();
        await flush();
        if (valid() && status !== "conflict") report(pending.size ? "pending" : "saved");
    } catch (error) { if (valid()) report("offline", error instanceof ApiRequestError && error.status < 500 ? error.message : ""); }
    finally { busy = false; }
    if (valid()) schedule(pending.size ? 1000 : 60000);
}
