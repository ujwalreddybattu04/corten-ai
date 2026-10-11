export interface SearchResult {
    query: string;
    answer: string;
    sources: Source[];
    relatedQuestions: string[];
    images?: SearchImage[];
    model: string;
}

export interface Source {
    url: string;
    title: string;
    domain: string;
    faviconUrl?: string;
    snippet?: string;
}

export interface SearchImage {
    url: string;
    alt: string;
    sourceUrl: string;
}

export type FocusMode = "all" | "academic" | "youtube" | "reddit" | "writing" | "math" | "social";
