import { create } from "zustand";

interface User {
    id: string;
    name: string;
    email: string;
    avatarUrl?: string;
    subscriptionTier: "free" | "pro";
}

interface AuthState {
    user: User | null;
    accessToken: string | null;
    isAuthenticated: boolean;
    setUser: (user: User, token: string) => void;
    logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
    user: null,
    accessToken: null,
    isAuthenticated: false,
    setUser: (user, accessToken) => set({ user, accessToken, isAuthenticated: true }),
    logout: () => set({ user: null, accessToken: null, isAuthenticated: false }),
}));
