export interface ModelConfig {
    id: string;
    label: string;
    provider: "openai" | "anthropic" | "google";
    description: string;
    isPro: boolean;
}

export const AVAILABLE_MODELS: ModelConfig[] = [
    {
        id: "gpt-4o",
        label: "GPT-4o",
        provider: "openai",
        description: "Fast and capable — great for most tasks",
        isPro: false,
    },
    {
        id: "gpt-4-turbo",
        label: "GPT-4 Turbo",
        provider: "openai",
        description: "More powerful reasoning",
        isPro: true,
    },
    {
        id: "claude-3.5-sonnet",
        label: "Claude 3.5 Sonnet",
        provider: "anthropic",
        description: "Balanced speed and intelligence",
        isPro: true,
    },
    {
        id: "claude-3-opus",
        label: "Claude 3 Opus",
        provider: "anthropic",
        description: "Most capable — complex analysis",
        isPro: true,
    },
    {
        id: "gemini-pro",
        label: "Gemini Pro",
        provider: "google",
        description: "Google's advanced model",
        isPro: true,
    },
];
