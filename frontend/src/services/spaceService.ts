import { api } from "@/lib/api";

export const spaceService = {
    list: () => api.get("/api/v1/spaces"),
    get: (id: string) => api.get(`/api/v1/spaces/${id}`),
    create: (name: string, description?: string) =>
        api.post("/api/v1/spaces", { name, description }),
    update: (id: string, data: object) => api.put(`/api/v1/spaces/${id}`, data),
    delete: (id: string) => api.delete(`/api/v1/spaces/${id}`),
    uploadFile: async (spaceId: string, file: File) => {
        const formData = new FormData();
        formData.append("file", file);
        return fetch(`/api/v1/spaces/${spaceId}/files`, { method: "POST", body: formData });
    },
};
