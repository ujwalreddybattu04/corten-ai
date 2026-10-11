import { api } from "@/lib/api";

export const discoverService = {
    getFeed: (category?: string) =>
        api.get(`/api/v1/discover${category ? `?category=${encodeURIComponent(category)}` : ""}`),
};
