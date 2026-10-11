"use client";

import { useRef } from "react";
import SearchBar from "./SearchBar";
import QuickActions from "./QuickActions";

// A thin client wrapper so page.tsx (server component) stays clean.
// Passes a callback from QuickActions → SearchBar so clicking a suggestion
// pre-fills the input and submits the search.
export default function HomeHero() {
    const searchBarRef = useRef<{ setQueryAndSubmit: (q: string) => void } | null>(null);

    const handleAction = (prompt: string) => {
        searchBarRef.current?.setQueryAndSubmit(prompt);
    };

    return (
        <>
            <SearchBar ref={searchBarRef} />
            <QuickActions onAction={handleAction} />
        </>
    );
}
