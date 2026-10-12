/** Shared Spaces client. The server is the source of truth for Spaces, members, files and shared threads. */
import { api, ApiRequestError } from "./api";

export type SpaceRole = "owner" | "editor" | "viewer";

export interface Space {
    id: string;
    name: string;
    description: string;
    instructions: string;
    icon: string;
    color: string;
    links: string[];
    webSearch: boolean;
    revision: number;
    role: SpaceRole;
    ownerName: string | null;
    legacyId: string | null;
    memberCount: number;
    threadCount: number;
    fileCount: number;
    createdAt: number;
    updatedAt: number;
}

export interface SpaceFields {
    name?: string;
    description?: string;
    instructions?: string;
    icon?: string;
    color?: string;
    links?: string[];
    webSearch?: boolean;
}

export interface SpaceMember {
    userId: string;
    name: string;
    email?: string;
    role: SpaceRole;
    avatarUrl: string | null;
    joinedAt: number;
    isYou: boolean;
}

export interface SpaceInvite {
    id: string;
    email: string | null;
    role: Exclude<SpaceRole, "owner">;
    kind: "email" | "link";
    createdAt: number;
    expiresAt: number;
}

export interface PendingInvitation extends SpaceInvite {
    spaceId: string;
    spaceName: string;
    icon: string;
    color: string;
    inviterName: string;
}

export interface InvitePreview {
    spaceId: string;
    name: string;
    description: string;
    icon: string;
    color: string;
    inviterName: string;
    role: Exclude<SpaceRole, "owner">;
    memberRole: SpaceRole | null;
    emailMismatch: boolean;
}

export interface SpaceThreadSummary {
    threadId: string;
    title: string;
    authorName: string;
    isAuthor: boolean;
    createdAt: number;
    updatedAt: number;
}

export interface SpaceThread {
    threadId: string;
    data: Record<string, unknown>;
    authorName: string;
    isAuthor: boolean;
    canEdit: boolean;
    updatedAt: number;
}

export interface SpaceFile {
    id: string;
    name: string;
    size: number;
    contentType: string;
    characters: number;
    uploadedBy: string | null;
    createdAt: number;
}

const base = (id: string) => `/api/v1/spaces/${encodeURIComponent(id)}`;

export const ROLE_RANK: Record<SpaceRole, number> = { viewer: 1, editor: 2, owner: 3 };
export const canEdit = (role?: SpaceRole | null) => !!role && ROLE_RANK[role] >= ROLE_RANK.editor;
export const ROLE_LABELS: Record<SpaceRole, string> = { owner: "Owner", editor: "Can edit", viewer: "Can view" };
export const ROLE_DESCRIPTIONS: Record<SpaceRole, string> = {
    owner: "Full control, including members and deletion",
    editor: "Ask questions, upload files and edit context",
    viewer: "Read threads, files and instructions",
};
export const MAX_FILE_BYTES = 25 * 1024 * 1024;
export const ACCEPTED_FILES = ".pdf,.docx,.pptx,.xlsx,.txt,.md,.markdown,.csv,.tsv,.json,.xml,.yaml,.yml,.html,.htm,.log,.rst,.tex," +
    ".py,.js,.ts,.tsx,.jsx,.java,.c,.h,.cpp,.hpp,.cs,.go,.rs,.rb,.php,.swift,.kt,.scala,.sql,.sh,.r,.m,.ini,.toml,.css,.srt,.vtt";

export const spacesApi = {
    list: () => api.get<{ items: Space[] }>("/api/v1/spaces").then(result => result.items),
    get: (id: string) => api.get<Space>(base(id)),
    create: (fields: SpaceFields & { name: string }) => api.post<Space>("/api/v1/spaces", fields),
    update: (space: Pick<Space, "id" | "revision">, fields: SpaceFields) =>
        api.patch<Space>(base(space.id), { ...fields, expected_revision: space.revision }),
    remove: (id: string) => api.delete<void>(base(id)),

    members: (id: string) => api.get<{ role: SpaceRole; members: SpaceMember[]; invites: SpaceInvite[] }>(`${base(id)}/members`),
    invite: (id: string, role: Exclude<SpaceRole, "owner">, email?: string) =>
        api.post<{ invite: SpaceInvite; token: string }>(`${base(id)}/invites`, { role, ...(email ? { email } : {}) }),
    revokeInvite: (id: string, inviteId: string) => api.delete<void>(`${base(id)}/invites/${encodeURIComponent(inviteId)}`),
    changeRole: (id: string, userId: string, role: SpaceRole) =>
        api.patch<void>(`${base(id)}/members/${encodeURIComponent(userId)}`, { role }),
    removeMember: (id: string, userId: string) => api.delete<void>(`${base(id)}/members/${encodeURIComponent(userId)}`),

    invitations: () => api.get<{ items: PendingInvitation[] }>("/api/v1/spaces/invitations").then(result => result.items),
    respond: (inviteId: string, accept: boolean) =>
        api.post<{ spaceId: string } | undefined>(`/api/v1/spaces/invitations/${encodeURIComponent(inviteId)}/${accept ? "accept" : "decline"}`),
    previewLink: (token: string) => api.get<InvitePreview>(`/api/v1/spaces/join/${encodeURIComponent(token)}`),
    acceptLink: (token: string) => api.post<{ spaceId: string }>(`/api/v1/spaces/join/${encodeURIComponent(token)}`),

    threads: (id: string, before?: number | null) =>
        api.get<{ items: SpaceThreadSummary[]; next: number | null }>(`${base(id)}/threads${before ? `?before=${before}` : ""}`),
    thread: (id: string, threadId: string) => api.get<SpaceThread>(`${base(id)}/threads/${encodeURIComponent(threadId)}`),
    saveThread: (id: string, threadId: string, data: { id: string } & Record<string, unknown>) =>
        api.put<{ threadId: string; title: string; updatedAt: number }>(`${base(id)}/threads/${encodeURIComponent(threadId)}`, { data }),
    removeThread: (id: string, threadId: string) => api.delete<void>(`${base(id)}/threads/${encodeURIComponent(threadId)}`),

    files: (id: string) => api.get<{ items: SpaceFile[] }>(`${base(id)}/files`).then(result => result.items),
    removeFile: (id: string, fileId: string) => api.delete<void>(`${base(id)}/files/${encodeURIComponent(fileId)}`),
    downloadUrl: (id: string, fileId: string) => `${base(id)}/files/${encodeURIComponent(fileId)}/download`,
    importLegacy: (spaces: unknown[]) => api.post<{ imported: Record<string, string> }>("/api/v1/spaces/import", { spaces }),
};

/** Upload with progress. An expired access token is refreshed once through the shared session client. */
export async function uploadSpaceFile(id: string, file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<SpaceFile> {
    try {
        return await sendUpload(id, file, onProgress, signal);
    } catch (error) {
        if (!(error instanceof ApiRequestError) || error.status !== 401) throw error;
        await api.get("/api/v1/auth/me");  // Refreshes the session or reports that sign-in is required.
        onProgress(0);
        return sendUpload(id, file, onProgress, signal);
    }
}

/** XMLHttpRequest is the only browser API that reports upload progress. */
function sendUpload(id: string, file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<SpaceFile> {
    return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", `${base(id)}/files`);
        request.withCredentials = true;
        request.responseType = "json";
        request.upload.onprogress = event => { if (event.lengthComputable) onProgress(event.loaded / event.total); };
        request.onload = () => {
            if (request.status >= 200 && request.status < 300) return resolve(request.response as SpaceFile);
            const detail = (request.response as { detail?: unknown } | null)?.detail;
            reject(new ApiRequestError(typeof detail === "string" ? detail
                : request.status === 401 ? "Your session expired. Sign in again and retry."
                : request.status === 413 ? "This file is larger than 25 MB." : "The upload failed. Please retry.", request.status));
        };
        request.onerror = () => reject(new ApiRequestError("The connection was interrupted. Please retry the upload.", 0));
        request.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
        signal?.addEventListener("abort", () => request.abort(), { once: true });
        const form = new FormData();
        form.append("file", file);
        request.send(form);
    });
}

export function inviteUrl(token: string): string {
    return `${window.location.origin}/spaces/join/${encodeURIComponent(token)}`;
}

export function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function relativeTime(ms: number, now = Date.now()): string {
    const seconds = Math.round((now - ms) / 1000);
    if (seconds < 60) return "Just now";
    const format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    for (const [unit, size] of [["minute", 60], ["hour", 3600], ["day", 86400]] as const) {
        const next = unit === "minute" ? 3600 : unit === "hour" ? 86400 : 7 * 86400;
        if (seconds < next) return format.format(-Math.floor(seconds / size), unit);
    }
    const date = new Date(ms);
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(date.getFullYear() !== new Date(now).getFullYear() ? { year: "numeric" } : {}) });
}

/** Normalize a user-entered reference link the same way the server does. */
export function normalizeLink(value: string): string | null {
    let url = value.trim();
    if (!url) return null;
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) url = "https://" + url;
    try {
        const parsed = new URL(url);
        if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname.includes(".") || parsed.username || parsed.password || url.length > 2048) return null;
        return parsed.href;
    } catch { return null; }
}

export function linkHost(link: string): string {
    try { return new URL(link).hostname.replace(/^www\./, ""); } catch { return link; }
}
