import { getStorageAccount } from "./accountStorage";
import type { AttachmentRef } from "./chatApi";
const PREFIX = "corten_question_draft:";
const TTL = 24 * 60 * 60 * 1000;

function validAttachments(value: unknown): AttachmentRef[] {
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is AttachmentRef => !!item && typeof item.id === "string" && typeof item.name === "string"
        && ["image", "document"].includes(item.kind) && typeof item.url === "string" && item.url.startsWith("/api/v1/attachments/")).slice(0, 10);
}

/** Carry submitted prompts in tab storage rather than URL/query logs. */
export function questionPath(query: string, focus = "all", space?: string, page: "search" | "report" = "search", attachments: AttachmentRef[] = []) {
    const text = query.trim();
    if (!text || text.length > 16000) throw new Error("Questions must contain 1–16,000 characters.");
    const parameters = new URLSearchParams({ focus });
    if (space) parameters.set("space", space);
    try {
        const id = crypto.randomUUID();
        sessionStorage.setItem(PREFIX+id, JSON.stringify({ query: text, owner: getStorageAccount(), created: Date.now(),
            private: sessionStorage.getItem("corten_private_mode") === "true", attachments: validAttachments(attachments) }));
        parameters.set("draft", id);
        return `/${page}?${parameters}`;
    } catch {
        if (attachments.length) throw new Error("Allow site storage for this tab to send attachments.");
        parameters.set(page === "report" ? "topic" : "q", text);
        const fallback = `/${page}?${parameters}`;
        if (fallback.length > 7500) throw new Error("Temporary tab storage is unavailable. Allow site storage before submitting a long question.");
        return fallback;
    }
}

export function readQuestionDraft(id: string | null): { query: string; private: boolean; attachments: AttachmentRef[] } | null {
    if (!id || !/^[0-9a-f-]{36}$/i.test(id) || typeof window === "undefined") return null;
    try {
        const item = JSON.parse(sessionStorage.getItem(PREFIX+id) || "null");
        if (!item || item.owner !== getStorageAccount() || typeof item.query !== "string" || !item.query.trim() || item.query.length > 16000 || !Number.isSafeInteger(item.created) || Date.now()-item.created > TTL || item.created > Date.now()+5000) return null;
        return { query: item.query, private: item.private === true, attachments: validAttachments(item.attachments) };
    } catch { return null; }
}

export function privateQuestionDraft(): boolean {
    if (typeof window === "undefined") return false;
    return readQuestionDraft(new URLSearchParams(window.location.search).get("draft"))?.private === true;
}

/** When the browser blocks the privacy setting, avoid persisting chat content. */
export function isPrivateChat(): boolean {
    if (typeof window === "undefined") return true;
    try { return sessionStorage.getItem("corten_private_mode") === "true" || privateQuestionDraft(); }
    catch { return true; }
}
