/** Chat capabilities: answer modes, attachments, generated files, personalization and memory. */
import { api } from "./api";
import { accountStorage } from "./accountStorage";
import { uploadWithProgress } from "./upload";

export type AnswerMode = "auto" | "fast" | "pro" | "think";

export const ANSWER_MODES: { value: AnswerMode; label: string; description: string }[] = [
    { value: "auto", label: "Auto", description: "Automatic selection" },
    { value: "fast", label: "Fast", description: "Quick responses" },
    { value: "pro", label: "Pro", description: "Analysis and long documents" },
    { value: "think", label: "Extended thinking", description: "Complex, multi-step questions" },
];

const MODE_KEY = "corten_answer_mode";
export function getAnswerMode(): AnswerMode {
    try {
        const value = accountStorage.getItem(MODE_KEY);
        return ANSWER_MODES.some(mode => mode.value === value) ? value as AnswerMode : "auto";
    } catch { return "auto"; }
}
export function setAnswerMode(mode: AnswerMode) {
    try { accountStorage.setItem(MODE_KEY, mode); } catch { /* The choice applies to this page only. */ }
    window.dispatchEvent(new Event("corten_answer_mode"));
}

/** An attachment as remembered in a conversation. The server keeps the file itself. */
export interface AttachmentRef {
    id: string;
    name: string;
    kind: "image" | "document" | "generated";
    url: string;
    size: number;
}

// The question points at an earlier image ("the chart", "this screenshot", "what colour…"). A request to make
// something ("build a dashboard with a bar chart") does not.
const VISUAL_REFERENCE = new RegExp(
    "\\b(?:the|this|that|these|those|my|your|its|their|same)\\s+(?:\\w+\\s+)?" +
    "(?:images?|pictures?|photos?|screenshots?|screens?|charts?|graphs?|figures?|diagrams?|logos?|slides?|scans?|drawings?|visuals?)\\b" +
    "|\\b(?:colou?rs?|looks? like|pictured|visible|shown in|see in)\\b", "i");

/** Attachments for a question, bounded like the server: this message's files, then earlier files newest first.
 *  The server reads earlier documents only when they are relevant to the question. Earlier images are sent only
 *  when the question refers to something visual: images require the vision model, which would otherwise
 *  override the user's chosen mode for unrelated follow-ups. */
export function conversationAttachments(current: AttachmentRef[], history: { attachments?: AttachmentRef[] }[], query = ""):
    { attachments: string[]; context: string[] } {
    const visual = VISUAL_REFERENCE.test(query);
    const attachments = [...new Set(current.filter(item => item.kind !== "generated").map(item => item.id))].slice(0, 10);
    const context: string[] = [];
    for (const item of history.slice().reverse().flatMap(turn => turn.attachments ?? [])) {
        if (item.kind === "generated" || attachments.includes(item.id) || context.includes(item.id)
            || (item.kind === "image" && !visual)) continue;
        context.push(item.id);
    }
    return { attachments, context: context.slice(0, 10 - attachments.length) };
}

export interface GeneratedFile extends AttachmentRef {
    format: "docx" | "pdf" | "xlsx" | "csv" | "pptx";
    label: string;
}

export const ATTACHMENT_ACCEPT = "image/png,image/jpeg,image/webp,image/gif,image/bmp,.pdf,.docx,.pptx,.xlsx,.txt,.md,.markdown," +
    ".csv,.tsv,.json,.xml,.yaml,.yml,.html,.htm,.log,.rst,.tex,.py,.js,.ts,.tsx,.jsx,.java,.c,.h,.cpp,.hpp,.cs,.go,.rs,.rb," +
    ".php,.swift,.kt,.scala,.sql,.sh,.r,.m,.ini,.toml,.css,.srt,.vtt";
export const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;
export const MAX_ATTACHMENTS = 10;
const ALLOWED = new Set(ATTACHMENT_ACCEPT.split(",").filter(item => item.startsWith(".")));
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp"]);

/** A reason the browser can reject a file before uploading it, or null. */
export function attachmentProblem(file: File): string | null {
    const extension = "." + (file.name.split(".").pop() ?? "").toLowerCase();
    const image = IMAGE_TYPES.has(file.type) || [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].includes(extension);
    if (!image && !ALLOWED.has(extension)) return "Unsupported type. Attach images, PDF, Office, HTML or text files.";
    if (file.size > MAX_ATTACHMENT_BYTES) return "Larger than 25 MB.";
    if (file.size === 0) return "This file is empty.";
    return null;
}

export function uploadAttachment(file: File, onProgress: (fraction: number) => void, signal?: AbortSignal) {
    return uploadWithProgress<AttachmentRef & { contentType: string }>("/api/v1/attachments", file, onProgress, signal)
        .then(result => ({ id: result.id, name: result.name, kind: result.kind, url: result.url, size: result.size }) as AttachmentRef);
}

export interface Preferences {
    style: "normal" | "concise" | "explanatory" | "formal" | "custom";
    custom_style: string;
    personal_instructions: string;
    memory_enabled: boolean;
}
export interface Memory { id: string; content: string; source: "manual" | "auto"; createdAt: number; updatedAt: number }
export interface StoredFile extends AttachmentRef { contentType: string; createdAt: number; expiresAt: number }

export const STYLES: { value: Preferences["style"]; label: string; description: string }[] = [
    { value: "normal", label: "Normal", description: "Balanced, default responses" },
    { value: "concise", label: "Concise", description: "Shorter answers that lead with the point" },
    { value: "explanatory", label: "Explanatory", description: "Teaches step by step with examples" },
    { value: "formal", label: "Formal", description: "Professional register for clients and executives" },
    { value: "custom", label: "Custom", description: "Describe your own style" },
];

export const personalizationApi = {
    get: () => api.get<Preferences>("/api/v1/me/personalization"),
    update: (changes: Partial<Preferences>) => api.put<Preferences>("/api/v1/me/personalization", changes),
    memories: () => api.get<{ items: Memory[] }>("/api/v1/me/memories").then(result => result.items),
    addMemory: (content: string) => api.post<Memory | { duplicate: true }>("/api/v1/me/memories", { content }),
    editMemory: (id: string, content: string) => api.patch<Memory>(`/api/v1/me/memories/${encodeURIComponent(id)}`, { content }),
    deleteMemory: (id: string) => api.delete<void>(`/api/v1/me/memories/${encodeURIComponent(id)}`),
    clearMemories: () => api.delete<{ removed: number }>("/api/v1/me/memories"),
    files: () => api.get<{ items: StoredFile[] }>("/api/v1/attachments").then(result => result.items),
    deleteFile: (id: string) => api.delete<void>(`/api/v1/attachments/${encodeURIComponent(id)}`),
};
