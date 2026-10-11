"use client";

import { useState, FormEvent } from "react";

interface FollowUpInputProps {
    onSubmit: (query: string) => void;
    isLoading?: boolean;
}

export default function FollowUpInput({ onSubmit, isLoading = false }: FollowUpInputProps) {
    const [query, setQuery] = useState("");

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (!query.trim() || isLoading) return;
        onSubmit(query);
        setQuery("");
    };

    return (
        <form className="follow-up-input" onSubmit={handleSubmit} id="follow-up-form">
            <input
                type="text"
                className="follow-up-input-field"
                placeholder="Ask a follow-up..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
                id="follow-up-input"
            />
            <button
                type="submit"
                className="follow-up-submit"
                disabled={isLoading || !query.trim()}
                id="follow-up-submit-btn"
            >
                →
            </button>
        </form>
    );
}
