export interface Thread {
    id: string;
    userId: string;
    spaceId?: string;
    title: string;
    focusMode: string;
    modelUsed: string;
    messages: Message[];
    createdAt: string;
    updatedAt: string;
}

export interface Message {
    id: string;
    threadId: string;
    role: "user" | "assistant";
    content: string;
    sources: Source[];
    modelUsed?: string;
    tokensUsed?: number;
    createdAt: string;
}

export interface Source {
    id: string;
    messageId: string;
    url: string;
    title: string;
    domain: string;
    faviconUrl?: string;
    snippet?: string;
    citationIndex: number;
}
