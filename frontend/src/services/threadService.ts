import { api } from "@/lib/api";
import type { Thread } from "@/types/thread";

export const threadService = {
    list: () => api.get<Thread[]>("/api/v1/threads"),
    get: (id: string) => api.get<Thread>(`/api/v1/threads/${id}`),
    create: (query: string, focusMode?: string) =>
        api.post<Thread>("/api/v1/threads", { query, focus_mode: focusMode }),
    sendMessage: (threadId: string, content: string) =>
        api.post(`/api/v1/threads/${threadId}/messages`, { content }),
    delete: (id: string) => api.delete(`/api/v1/threads/${id}`),
};
