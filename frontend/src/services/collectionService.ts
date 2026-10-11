import { api } from "@/lib/api";

export const collectionService = {
    list: () => api.get("/api/v1/collections"),
    create: (name: string) => api.post("/api/v1/collections", { name }),
    update: (id: string, threadIds: string[]) =>
        api.put(`/api/v1/collections/${id}`, { thread_ids: threadIds }),
    delete: (id: string) => api.delete(`/api/v1/collections/${id}`),
};
