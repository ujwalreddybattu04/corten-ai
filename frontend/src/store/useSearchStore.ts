import { create } from "zustand";

interface SearchState {
    query: string;
    focusMode: string;
    isSearching: boolean;
    setQuery: (query: string) => void;
    setFocusMode: (mode: string) => void;
    setIsSearching: (isSearching: boolean) => void;
    reset: () => void;
}

export const useSearchStore = create<SearchState>((set) => ({
    query: "",
    focusMode: "all",
    isSearching: false,
    setQuery: (query) => set({ query }),
    setFocusMode: (focusMode) => set({ focusMode }),
    setIsSearching: (isSearching) => set({ isSearching }),
    reset: () => set({ query: "", focusMode: "all", isSearching: false }),
}));
