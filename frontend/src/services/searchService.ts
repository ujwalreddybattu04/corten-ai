import { api } from "@/lib/api";

export const searchService = {
    search: async (query: string, focusMode: string = "all", model?: string) => {
        return api.post("/api/v1/search", { query, focus_mode: focusMode, model });
    },

    getSuggestions: async (query: string) => {
        return api.post<string[]>("/api/v1/search/suggestions", { query });
    },
};
