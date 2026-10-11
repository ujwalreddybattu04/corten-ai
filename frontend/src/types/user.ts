export interface User {
    id: string;
    name: string;
    email: string;
    avatarUrl?: string;
    subscriptionTier: "free" | "pro";
    preferences: UserPreferences;
    createdAt: string;
    updatedAt: string;
}

export interface UserPreferences {
    defaultModel: string;
    theme: "light" | "dark";
    language: string;
    defaultFocusMode: string;
}
