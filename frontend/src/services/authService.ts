import { api } from "@/lib/api";

export const authService = {
    login: (email: string, password: string) =>
        api.post("/api/v1/auth/login", { email, password }),
    register: (name: string, email: string, password: string) =>
        api.post("/api/v1/auth/register", { name, email, password }),
    refresh: (refreshToken: string) =>
        api.post("/api/v1/auth/refresh", { refresh_token: refreshToken }),
    oauthLogin: (provider: string, code: string) =>
        api.post(`/api/v1/auth/oauth/${provider}`, { code }),
};
