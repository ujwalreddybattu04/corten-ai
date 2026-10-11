import { create } from "zustand";
import type { Thread, Message } from "@/types/thread";

interface ThreadState {
    currentThread: Thread | null;
    messages: Message[];
    isStreaming: boolean;
    setCurrentThread: (thread: Thread) => void;
    addMessage: (message: Message) => void;
    setIsStreaming: (isStreaming: boolean) => void;
    clearThread: () => void;
}

export const useThreadStore = create<ThreadState>((set) => ({
    currentThread: null,
    messages: [],
    isStreaming: false,
    setCurrentThread: (thread) => set({ currentThread: thread, messages: thread.messages || [] }),
    addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
    setIsStreaming: (isStreaming) => set({ isStreaming }),
    clearThread: () => set({ currentThread: null, messages: [], isStreaming: false }),
}));
