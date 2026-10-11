"use client";

import { useState, useEffect, useRef, forwardRef, useImperativeHandle, FormEvent, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { FOCUS_MODES } from "@/config/focusModes";
import { Code, MessageSquare, Play, Users, FileText } from "lucide-react";

const PRIMARY_MODES = ["all", "academic", "writing", "math"];
const primaryFocusModes = FOCUS_MODES.filter(m => PRIMARY_MODES.includes(m.value));
const moreFocusModes = FOCUS_MODES.filter(m => !PRIMARY_MODES.includes(m.value));

const MORE_ICONS: Record<string, ReactNode> = {
    code: <Code size={15} />,
    reddit: <MessageSquare size={15} />,
    youtube: <Play size={15} />,
    social: <Users size={15} />,
};

export interface SearchBarHandle {
    setQueryAndSubmit: (q: string) => void;
}

const SearchBar = forwardRef<SearchBarHandle, object>(function SearchBar(_, ref) {
    const [query, setQuery] = useState("");
    const [focusMode, setFocusMode] = useState("all");
    const [moreOpen, setMoreOpen] = useState(false);
    const router = useRouter();
    const inputRef = useRef<HTMLInputElement>(null);
    const moreRef = useRef<HTMLDivElement>(null);

    useImperativeHandle(ref, () => ({
        setQueryAndSubmit(q: string) {
            setQuery(q);
            inputRef.current?.focus();
            // Short delay so React flushes the new value before navigation
            setTimeout(() => {
                router.push(`/search?q=${encodeURIComponent(q)}&focus=all`);
            }, 60);
        },
    }));

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                inputRef.current?.focus();
            }
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, []);

    // Close "more" dropdown on outside click
    useEffect(() => {
        if (!moreOpen) return;
        const handler = (e: MouseEvent) => {
            if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
                setMoreOpen(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [moreOpen]);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (!query.trim()) return;
        router.push(`/search?q=${encodeURIComponent(query)}&focus=${focusMode}`);
    };

    return (
        <form className="search-bar" onSubmit={handleSubmit} id="search-bar">
            <div className="search-bar-container">
                {/* Input Row */}
                <div className="search-input-row">
                    <input
                        ref={inputRef}
                        type="text"
                        className="search-bar-input"
                        placeholder="What's on your mind?"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        autoFocus
                        autoComplete="off"
                        autoCorrect="off"
                        autoCapitalize="off"
                        spellCheck={false}
                        id="search-input"
                    />
                </div>

                {/* Focus Mode + Model + Submit Row */}
                <div className="search-focus-row">
                    {/* Add button */}
                    <button type="button" className="focus-add-btn" title="Add file or connector" id="focus-add-btn">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14" /></svg>
                    </button>

                    {/* Focus tabs */}
                    <div className="focus-tabs">
                        {primaryFocusModes.map((mode) => (
                            <button
                                key={mode.value}
                                type="button"
                                className={`focus-tab ${focusMode === mode.value ? "active" : ""}`}
                                onClick={() => setFocusMode(mode.value)}
                                id={`focus-tab-${mode.value}`}
                                title={mode.description}
                            >
                                {mode.label}
                            </button>
                        ))}

                        {/* If an extra mode is active, show it as a tab */}
                        {moreFocusModes.some(m => m.value === focusMode) && (
                            <button
                                type="button"
                                className="focus-tab active"
                            >
                                {FOCUS_MODES.find(m => m.value === focusMode)?.label}
                            </button>
                        )}

                        {/* More dropdown */}
                        <div className="focus-more-wrapper" ref={moreRef}>
                            <button
                                type="button"
                                className={`focus-tab focus-more-btn ${moreOpen ? "active" : ""}`}
                                onClick={() => setMoreOpen(!moreOpen)}
                                title="More focus modes"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
                            </button>
                            {moreOpen && (
                                <div className="focus-more-dropdown">
                                    {moreFocusModes.map((mode) => (
                                        <button
                                            key={mode.value}
                                            type="button"
                                            className={`focus-more-item ${focusMode === mode.value ? "active" : ""}`}
                                            onClick={() => { setFocusMode(mode.value); setMoreOpen(false); }}
                                        >
                                            <span className="focus-more-icon">{MORE_ICONS[mode.value]}</span>
                                            <div className="focus-more-text">
                                                <span className="focus-more-label">{mode.label}</span>
                                                <span className="focus-more-desc">{mode.description}</span>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Model selector + Report + Submit */}
                    <div className="search-model-selector">
                        <button type="button" className="model-dropdown-btn" id="model-selector-btn">
                            Auto <span className="model-dropdown-arrow">▾</span>
                        </button>
                        <button
                            type="button"
                            className="search-report-btn"
                            title="Generate detailed report"
                            onClick={() => {
                                if (!query.trim()) return;
                                router.push(`/report?topic=${encodeURIComponent(query)}&focus=${focusMode}`);
                            }}
                        >
                            <FileText size={15} />
                        </button>
                        <button type="submit" className="search-submit-btn" id="search-submit-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>
                        </button>
                    </div>
                </div>
            </div>
        </form>
    );
});

export default SearchBar;
