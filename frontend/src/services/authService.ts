import { api } from "@/lib/api";
export const authService = {
    login: (email: string, password: string, remember = false) => api.post("/api/v1/auth/login", { email: email.trim(), password, remember_me: remember }),
    register: (name: string, email: string, password: string) => api.post("/api/v1/auth/register", { name: name.trim(), email: email.trim(), password }),
    refresh: () => api.post("/api/v1/auth/refresh", {}),
    logout: () => api.post("/api/v1/auth/logout", {}),
};