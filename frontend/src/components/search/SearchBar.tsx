"use client";

import { useState, useEffect, useRef, forwardRef, useImperativeHandle, FormEvent, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { questionPath } from "@/lib/questionDrafts";
import { FOCUS_MODES } from "@/config/focusModes";
import { Code, MessageSquare, Play, Users, FileText } from "lucide-react";
import { useAttachments } from "@/hooks/useAttachments";
import { AttachButton, AttachmentTray, ModeMenu, filesFromTransfer } from "@/components/chat/ComposerControls";

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
    const [submitError, setSubmitError] = useState("");
    const router = useRouter();
    const inputRef = useRef<HTMLInputElement>(null);
    const moreRef = useRef<HTMLDivElement>(null);
    const attachments = useAttachments();
    const [dragging, setDragging] = useState(false);

    useImperativeHandle(ref, () => ({
        setQueryAndSubmit(q: string) {
            setQuery(q);
            inputRef.current?.focus();
            // Short delay so React flushes the new value before navigation
            setTimeout(() => {
                try { router.push(questionPath(q)); } catch (error) { setSubmitError(error instanceof Error ? error.message : "Unable to open this question."); }
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
        if (attachments.uploading) { setSubmitError("Wait for your files to finish uploading."); return; }
        try { setSubmitError(""); router.push(questionPath(query, focusMode, undefined, "search", attachments.ready)); } catch (error) { setSubmitError(error instanceof Error ? error.message : "Unable to submit this question."); }
    };

    return (
        <form className={`search-bar ${dragging ? "cx-dropping" : ""}`} onSubmit={handleSubmit} id="search-bar"
            onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
            onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
            onDrop={event => { const files = filesFromTransfer(event.dataTransfer); if (files.length) { event.preventDefault(); attachments.add(files); } setDragging(false); }}>
            <div className="search-bar-container">
                {submitError && <p role="alert" className="cx-composer-error">{submitError}</p>}
                <AttachmentTray items={attachments.items} onRemove={attachments.remove} />
                {/* Input Row */}
                <div className="search-input-row">
                    <input
                        ref={inputRef}
                        type="text"
                        className="search-bar-input"
                        placeholder={attachments.items.length ? "Ask about your files…" : "What's on your mind?"}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onPaste={event => { const files = filesFromTransfer(event.clipboardData); if (files.length) { event.preventDefault(); attachments.add(files); } }}
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
                        <AttachButton onFiles={attachments.add} />
                        <ModeMenu />
                        <button
                            type="button"
                            className="search-report-btn"
                            disabled={!query.trim()}
                            title="Generate detailed report"
                            onClick={() => {
                                if (!query.trim()) return;
                                try { router.push(questionPath(query, focusMode, undefined, "report")); } catch (error) { setSubmitError(error instanceof Error ? error.message : "Unable to open the report."); }
                            }}
                        >
                            <FileText size={15} />
                        </button>
                        <button type="submit" className="search-submit-btn" id="search-submit-btn" aria-label="Ask" disabled={attachments.uploading}>
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>
                        </button>
                    </div>
                </div>
            </div>
        </form>
    );
});

export default SearchBar;
