"use client";
import { useRef, useEffect, memo, useMemo, useState, useCallback } from "react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SearchSource, ResearchStep } from "@/hooks/useSearch";
import { ResearchProgress } from "./ResearchProgress";
import CodeRunnerModal, { isRunnable } from "./CodeRunnerModal";
import HtmlPreviewModal from "./HtmlPreviewModal";
import { preloadPyodide } from "@/hooks/usePyodideWorker";
import { accountStorage } from "@/lib/accountStorage";
import { splitArtifacts, type Artifact } from "@/lib/artifacts";
import type { GeneratedFile } from "@/lib/chatApi";
import { ArtifactCard, FileCards, ThinkingPanel, linkCitations } from "@/components/chat/AnswerExtras";
import { protectCurrency } from "@/lib/currency";
import { citationNumbers, sourceLabel, stripLeadingHeading } from "@/lib/citations";

// Premium Formatting Dependencies
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

// Syntax Highlighting
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { CornerDownRight } from "lucide-react";

// ── Standalone sub-components so hooks are never called conditionally ──────

const PROGRAMMING_LANGS = new Set(["python","javascript","typescript","js","ts","java","c","cpp","c++","rust","go","ruby","php","swift","kotlin","bash","sh","sql"]);

function extractEmailText(raw: string): string {
    return raw
        .replace(/^def\s+\w+\([^)]*\):\s*/m, "")
        .replace(/^\s*(email_body|body|template|text|content|email)\s*=\s*f?["']{1,3}/m, "")
        .replace(/["']{1,3}\s*$/, "")
        .replace(/^\s*return\s+\w+\s*$/m, "")
        .replace(/^[ \t]{4}/gm, "")
        .trim();
}

function EmailTemplateBlock({ codeString }: { codeString: string }) {
    const [copied, setCopied] = useState(false);
    const emailText = extractEmailText(codeString);
    const copy = () => {
        navigator.clipboard?.writeText(emailText).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); }).catch(() => { /* The displayed email can be selected and copied. */ });
    };
    return (
        <div className="answer-email-block">
            <div className="answer-email-block-header">
                <div className="answer-email-block-label">
                    <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
                    <span>Email Template</span>
                </div>
                <button className="answer-copy-code-btn" onClick={copy}>
                    {copied
                        ? <><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Copied</>
                        : <><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg> Copy</>}
                </button>
            </div>
            <pre className="answer-email-block-body">{emailText}</pre>
        </div>
    );
}

interface CodeBlockProps {
    codeString: string;
    language: string;
    lineClass: string;
    onRun: () => void;
    onPreview: () => void;
    canRun: boolean;
    isHtml: boolean;
}
function SyntaxCodeBlock({ codeString, language, lineClass, onRun, onPreview, canRun, isHtml }: CodeBlockProps) {
    const [copied, setCopied] = useState(false);
    const copy = () => {
        navigator.clipboard?.writeText(codeString).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); }).catch(() => { /* The displayed code remains available for copying. */ });
    };
    return (
        <div className={`answer-code-container ${lineClass}`}>
            <div className="answer-code-header">
                <span className="answer-code-lang">{language || "code"}</span>
                <div className="answer-code-header-actions">
                    {isHtml && (
                        <button className="answer-preview-btn" onClick={onPreview} title="Preview HTML">
                            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
                                <circle cx="12" cy="12" r="3"/>
                            </svg>
                            Preview
                        </button>
                    )}
                    {canRun && (
                        <button className="answer-run-btn" onClick={onRun} title="Run code">
                            <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                                <polygon points="5 3 19 12 5 21 5 3" />
                            </svg>
                            Run
                        </button>
                    )}
                    <button className="answer-copy-code-btn" onClick={copy}>
                        {copied ? (
                            <div className="answer-copy-code-success">
                                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                                <span>Copied</span>
                            </div>
                        ) : (
                            <div className="answer-copy-code-default">
                                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <rect width="14" height="14" x="8" y="8" rx="2" ry="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                                </svg>
                                <span>Copy</span>
                            </div>
                        )}
                    </button>
                </div>
            </div>
            <SyntaxHighlighter
                language={language || "text"}
                style={oneDark}
                customStyle={{ margin: 0, padding: "16px", background: "transparent", fontSize: "0.85rem", lineHeight: "1.6", borderRadius: "0 0 12px 12px" }}
                wrapLongLines={true}
                PreTag="div"
            >
                {codeString}
            </SyntaxHighlighter>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────

interface AnswerStreamProps {
    query?: string;
    content: string;
    isStreaming: boolean;
    sources: SearchSource[];
    researchSteps?: ResearchStep[];
    thoughtTime?: number;
    onCopy?: () => void;
    sourcesPanelOpen?: boolean;
    setSourcesPanelOpen?: (open: boolean) => void;
    relatedQuestions?: string[];
    onRelatedSelect?: (question: string) => void;
    onRegenerate?: () => void;
    /** Extended thinking reasoning, files Corten created, and artifact panel wiring. */
    reasoning?: string;
    files?: GeneratedFile[];
    activeArtifactTitle?: string | null;
    onOpenArtifact?: (artifact: Artifact) => void;
}

const AnswerStream = memo(({
    query = "",
    content,
    isStreaming,
    sources,
    researchSteps = [],
    thoughtTime = 0,
    onCopy,
    sourcesPanelOpen: externalSourcesPanelOpen,
    setSourcesPanelOpen: externalSetSourcesPanelOpen,
    relatedQuestions = [],
    onRelatedSelect,
    onRegenerate,
    reasoning = "",
    files = [],
    activeArtifactTitle = null,
    onOpenArtifact,
}: AnswerStreamProps) => {
    const contentRef = useRef<HTMLDivElement>(null);
    const [localCopied, setLocalCopied] = useState(false);
    const [localSourcesPanelOpen, setLocalSourcesPanelOpen] = useState(false);
    const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
    const feedbackKey = useMemo(() => {
        let hash = 2166136261;
        for (const char of query + "\n" + content) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
        return String(hash >>> 0);
    }, [query, content]);
    useEffect(() => {
        try { setFeedback(JSON.parse(accountStorage.getItem("corten_answer_feedback") || "{}")[feedbackKey] || null); } catch { /* Optional feedback never affects the answer. */ }
    }, [feedbackKey]);
    const vote = (value: "up" | "down") => {
        try {
            const stored = JSON.parse(accountStorage.getItem("corten_answer_feedback") || "{}");
            const next = feedback === value ? null : value;
            if (sessionStorage.getItem("corten_private_mode") === "true") { setFeedback(next); return; }
            if (next) stored[feedbackKey] = next; else delete stored[feedbackKey];
            accountStorage.setItem("corten_answer_feedback", JSON.stringify(Object.fromEntries(Object.entries(stored).slice(-500))));
            setFeedback(next);
        } catch { /* Keep the current feedback when device storage is unavailable. */ }
    };

    // Code runner modal state
    const [runnerState, setRunnerState] = useState<{ code: string; language: string } | null>(null);
    // HTML preview modal state
    const [previewCode, setPreviewCode] = useState<string | null>(null);
    const setPreviewCodeRef = useRef(setPreviewCode);
    setPreviewCodeRef.current = setPreviewCode;
    // Stable ref so useMemo doesn't need to re-run when setRunnerState changes
    const setRunnerStateRef = useRef(setRunnerState);
    setRunnerStateRef.current = setRunnerState;

    // Load the Python runtime only when a Python example is actually present.
    const hasPython = /```(?:python|py)\s/i.test(content);
    useEffect(() => { if (hasPython) preloadPyodide(); }, [hasPython]);
    const sourcesPanelOpen = externalSourcesPanelOpen !== undefined ? externalSourcesPanelOpen : localSourcesPanelOpen;
    const setSourcesPanelOpen = externalSetSourcesPanelOpen !== undefined ? externalSetSourcesPanelOpen : setLocalSourcesPanelOpen;
    // Markdown is the answer. Never infer a cut point from headings, links or numbers.
    const processedContent = content;
    // Artifacts render as cards (opened in the side panel); everything else is Markdown.
    const segments = useMemo(() => splitArtifacts(processedContent), [processedContent]);

    // --- MANUAL SCROLL OVERRIDE ---
    const userScrolledUpRef = useRef(false);

    // Auto-scroll: track the cursor so the text generation stays in view without forcing a full bottom scroll
    useEffect(() => {
        if (!isStreaming) {
            userScrolledUpRef.current = false;
            return;
        }

        const scrollable = document.querySelector('.sp-content');
        if (!scrollable) return;

        // Listener to detect manual scroll up
        const handleScroll = () => {
            const { scrollTop, scrollHeight, clientHeight } = scrollable;
            // threshold of 100px from bottom to consider "at bottom"
            const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;

            if (!isAtBottom) {
                userScrolledUpRef.current = true;
            } else {
                userScrolledUpRef.current = false;
            }
        };

        scrollable.addEventListener('scroll', handleScroll);

        const cursor = scrollable.querySelector('.answer-cursor');
        if (cursor && !userScrolledUpRef.current) {
            const cursorRect = cursor.getBoundingClientRect();
            const scrollableRect = scrollable.getBoundingClientRect();

            // If the streaming cursor hits the bottom of the visible area, push the scroll down gently
            if (cursorRect.bottom > scrollableRect.bottom - 40) {
                // We only push down by the exact amount needed to keep the cursor visible
                scrollable.scrollBy({ top: cursorRect.bottom - scrollableRect.bottom + 40, behavior: "smooth" });
            }
        }

        return () => {
            scrollable.removeEventListener('scroll', handleScroll);
        };
    }, [content, isStreaming]);

    const handleCopy = () => {
        navigator.clipboard?.writeText(content).then(() => { setLocalCopied(true); setTimeout(() => setLocalCopied(false), 2000); onCopy?.(); }).catch(() => { /* Never claim that a blocked copy succeeded. */ });
    };

    // Memoize markdown components so they aren't recreated on every render
    const markdownComponents = useMemo(() => {
        const lineClass = isStreaming ? " liquid-line" : "";
        return {
            p: ({ children }: any) => (
                <p className={`answer-paragraph${lineClass}`}>{children}</p>
            ),
            h2: ({ children }: any) => (
                <h2 className={`answer-h2${lineClass}`}>{children}</h2>
            ),
            h3: ({ children }: any) => (
                <h3 className={`answer-h3${lineClass}`}>{children}</h3>
            ),
            ul: ({ children }: any) => (
                <ul className="answer-list">{children}</ul>
            ),
            ol: ({ children }: any) => (
                <ol className="answer-list answer-list-ordered">{children}</ol>
            ),
            li: ({ children }: any) => (
                <li className={`answer-list-item${lineClass}`}>{children}</li>
            ),
            code: ({ children, className }: any) => {
                const isBlock = className?.includes("language-");
                const language = className ? className.replace("language-", "") : "";

                if (isBlock) {
                    const codeString = String(children).replace(/\n$/, "");
                    const lang = language.toLowerCase();
                    const hasEmailGreeting = /\b(Dear\s|Hello\s|Hi\s)/i.test(codeString);
                    const hasEmailClosing = /\b(Sincerely,|Best regards,|Regards,|Yours truly,|Thank you,|Best,|Warm regards,)/i.test(codeString);
                    const isWrappedEmail = PROGRAMMING_LANGS.has(lang) && hasEmailGreeting && hasEmailClosing;

                    if (isWrappedEmail) {
                        return <EmailTemplateBlock codeString={codeString} />;
                    }

                    const isHtml = lang === "html" || lang === "htm" || lang === "svg";
                    const canRun = !isHtml && isRunnable(language);
                    return (
                        <SyntaxCodeBlock
                            codeString={codeString}
                            language={language}
                            lineClass={lineClass}
                            onRun={() => setRunnerStateRef.current({ code: codeString, language })}
                            onPreview={() => setPreviewCodeRef.current(codeString)}
                            canRun={canRun}
                            isHtml={isHtml}
                        />
                    );
                }
                return <code className="answer-code-inline">{children}</code>;
            },
            strong: ({ children }: any) => (
                <strong className="answer-bold">{children}</strong>
            ),
            a: ({ href, children }: any) => {
                let decodedHref = href || "";
                try { decodedHref = decodeURIComponent(decodedHref); } catch { /* A literal % is valid in a link label or source. */ }
                // Hide only explicit internal citation links. Ordinary numeric links remain intact.
                if (/^(?:citation|cite):\s*\d+(?:\s*,\s*\d+)*$/i.test(decodedHref.trim())) return <></>;
                // A run of citations is one source pill: the first source's site, "+N" for the others.
                const numbers = citationNumbers(decodedHref);
                if (numbers) {
                    const cited = numbers.map(number => sources.find(item => item.citationIndex === number) ?? sources[number - 1])
                        .filter((source, index, all): source is SearchSource => !!source?.url && all.findIndex(other => other?.url === source.url) === index);
                    // Sources arrive before the answer; a citation with no known source is not shown at all.
                    if (!cited.length) return <></>;
                    const [first, ...others] = cited;
                    const names = cited.map(source => `${source.title || sourceLabel(source)} (${sourceLabel(source)})`);
                    return (
                        <a href={first.url} className="cx-cite" target="_blank" rel="noopener noreferrer" title={names.join("\n")}
                            aria-label={`Sources: ${names.join("; ")}`}>
                            {first.favicon && (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img className="cx-cite-icon" src={first.favicon} alt="" width={12} height={12} loading="lazy"
                                    onError={event => { (event.target as HTMLImageElement).style.display = "none"; }} />
                            )}
                            <span className="cx-cite-label">{sourceLabel(first)}</span>
                            {others.length > 0 && <span className="cx-cite-more">+{others.length}</span>}
                        </a>
                    );
                }

                // Standard text hyperlink
                return <a href={href} className="answer-link" target="_blank" rel="noopener noreferrer">{children}</a>;
            },
            table: ({ children }: any) => (
                <div className="answer-table-wrapper">
                    <table className="answer-table">{children}</table>
                </div>
            ),
            thead: ({ children }: any) => (
                <thead className="answer-thead">{children}</thead>
            ),
            tbody: ({ children }: any) => (
                <tbody className="answer-tbody">{children}</tbody>
            ),
            tr: ({ children }: any) => (
                <tr className="answer-tr">{children}</tr>
            ),
            th: ({ children }: any) => (
                <th className="answer-th">{children}</th>
            ),
            td: ({ children }: any) => (
                <td className="answer-td">{children}</td>
            ),
        };
    }, [sources, isStreaming]);

    return (
        <>
        {runnerState && (
            <CodeRunnerModal
                code={runnerState.code}
                language={runnerState.language}
                onClose={() => setRunnerState(null)}
            />
        )}
        {previewCode !== null && (
            <HtmlPreviewModal
                code={previewCode}
                onClose={() => setPreviewCode(null)}
            />
        )}
        <div className="answer-stream" id="answer-stream" ref={contentRef}>
            {/* Research Progress / Thinking State */}
            <ResearchProgress
                query={query}
                steps={researchSteps}
                isComplete={!isStreaming && content.length > 0}
                isStreaming={isStreaming}
                isAnswerStarted={content.length > 0}
                sources={sources}
                thoughtTime={thoughtTime}
            />

            {/* Answer section — clean render, no layout animations during streaming */}
            {(content.trim().length > 0 || isStreaming) && (
                <div className="answer-container-wrapper">
                    {/* Answer header bar */}
                    <div className="answer-stream-header">
                        <div className="answer-stream-label">
                            <div className={isStreaming ? "answer-icon-pulse" : ""}>
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                                </svg>
                            </div>
                            <span style={{ fontWeight: 600, letterSpacing: "-0.01em" }}>Answer</span>
                            {isStreaming && <span className="answer-streaming-dot" />}
                        </div>
                        <div className="answer-stream-actions">
                            <button
                                className="answer-action-btn"
                                onClick={handleCopy}
                                title="Copy answer"
                                aria-label="Copy answer"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <rect width="14" height="14" x="8" y="8" rx="2" ry="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                                </svg>
                            </button>
                            <button
                                className="answer-action-btn"
                                title="Share"
                                aria-label="Share answer"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><line x1="8.59" x2="15.42" y1="13.51" y2="17.49" /><line x1="15.41" x2="8.59" y1="6.51" y2="10.49" />
                                </svg>
                            </button>
                        </div>
                    </div>

                    <ThinkingPanel reasoning={reasoning} active={isStreaming && !content.trim()} />

                    {/* Answer content — pure CSS transitions, no Framer Motion layout thrashing */}
                    <div className="answer-stream-content">
                        {segments.map((segment, index) => segment.kind === "artifact" ? (
                            <ArtifactCard key={segment.key} artifact={segment} active={activeArtifactTitle === segment.title}
                                onOpen={() => onOpenArtifact?.(segment)} />
                        ) : (
                            <ReactMarkdown
                                key={`text-${index}`}
                                remarkPlugins={[remarkGfm, remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={markdownComponents}
                            >
                                {linkCitations(protectCurrency(index === 0 ? stripLeadingHeading(segment.text, sources.length > 0) : segment.text))}
                            </ReactMarkdown>
                        ))}
                        <FileCards files={files} />

                        {/* Streaming cursor */}
                        {isStreaming && (
                            <span className="answer-cursor" aria-hidden="true">▋</span>
                        )}
                    </div>

                    {/* Action row — Scoped per-message, delayed while streaming */}
                    {(content.trim().length > 0 || sources.length > 0) && !isStreaming && (
                        <div className="sp-action-row">
                            <div className="sp-action-left">
                                {/* Sources action button - Now first on the left! */}
                                {sources.length > 0 && (
                                    <button
                                        className={`sp-sources-action-btn ${sourcesPanelOpen ? "active" : ""}`}
                                        onClick={() => setSourcesPanelOpen(!sourcesPanelOpen)}
                                        aria-label="View sources"
                                    >
                                        <div className="sp-sources-pill-favicons">
                                            {sources.slice(0, 3).map((source, i) => (
                                                <div
                                                    key={i}
                                                    className="sp-source-pill-icon"
                                                    style={{ zIndex: 3 - i }}
                                                >
                                                    {source.favicon ? (
                                                        <img src={source.favicon} alt="" />
                                                    ) : (
                                                        <span className="sp-source-pill-letter">
                                                            {(source.domain || source.url || "?").charAt(0).toUpperCase()}
                                                        </span>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                        <span className="sp-sources-pill-text">
                                            {sources.length} {sources.length === 1 ? "source" : "sources"}
                                        </span>
                                    </button>
                                )}
                                <div className="sp-action-divider" />
                                <button className="sp-icon-btn" onClick={handleCopy} title={localCopied ? "Copied!" : "Copy"}>
                                    {localCopied ? (
                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12" /></svg>
                                    ) : (
                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect width="14" height="14" x="8" y="8" rx="2" ry="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" /></svg>
                                    )}
                                </button>
                                {onRegenerate && <button className="sp-icon-btn" title="Regenerate answer" onClick={onRegenerate}>
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" /></svg>
                                </button>}
                            </div>
                            <div className="sp-action-right">
                                <button className="sp-icon-btn" title="Mark helpful" aria-label="Mark helpful" aria-pressed={feedback === "up"} onClick={() => vote("up")}>
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M7 10v12" /><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" /></svg>
                                </button>
                                <button className="sp-icon-btn" title="Mark unhelpful" aria-label="Mark unhelpful" aria-pressed={feedback === "down"} onClick={() => vote("down")}>
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M17 14V2" /><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" /></svg>
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Follow-ups - Now beautifully constrained to the exact AnswerStream width */}
                    {!isStreaming && relatedQuestions.length > 0 && (
                        <div className="sp-followups">
                            <div className="sp-followups-title">Follow-ups</div>
                            <div className="sp-followups-list">
                                {relatedQuestions.map((q, i) => (
                                    <button
                                        key={i}
                                        className="sp-followup-item"
                                        onClick={() => onRelatedSelect?.(q)}
                                        id={`followup-${i}`}
                                    >
                                        <span className="sp-followup-arrow">
                                            <CornerDownRight size={16} strokeWidth={2} />
                                        </span>
                                        <span className="sp-followup-text">{q}</span>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                </div>
            )}
        </div>
        </>
    );
});

AnswerStream.displayName = "AnswerStream";
export default AnswerStream;
