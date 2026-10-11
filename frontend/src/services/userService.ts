import { api } from "@/lib/api";

export const userService = {
    getProfile: () => api.get("/api/v1/users/me"),
    updateProfile: (data: object) => api.put("/api/v1/users/me", data),
};
