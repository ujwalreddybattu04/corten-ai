"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { X, Copy, Check, Download, Maximize2, Minimize2, ChevronLeft, ChevronRight, AlertTriangle, Wand2, Loader2 } from "lucide-react";
import { ARTIFACT_LABELS, artifactFilename, sandboxDocument, sandboxPermissions, type Artifact } from "@/lib/artifacts";
import { ARTIFACT_ICONS } from "./AnswerExtras";

const LANGUAGES: Record<string, string> = { react: "jsx", html: "markup", mermaid: "markdown", svg: "markup", markdown: "markdown" };

/** Side panel that previews an artifact in an isolated sandbox, with code, versions, copy and download. */
export default function ArtifactPanel({ versions, index, onIndex, onClose, onFix, fixDisabled }: {
    versions: Artifact[]; index: number; onIndex: (index: number) => void; onClose: () => void;
    onFix: (request: string) => void; fixDisabled?: boolean;
}) {
    const artifact = versions[Math.min(index, versions.length - 1)];
    const previewable = artifact.type !== "code";
    // Tab and run status belong to one artifact version; switching versions resets them.
    const [tabChoice, setTabChoice] = useState<{ key: string; tab: "preview" | "code" } | null>(null);
    const tab = tabChoice?.key === artifact.key ? tabChoice.tab : previewable ? "preview" : "code";
    const setTab = (next: "preview" | "code") => setTabChoice({ key: artifact.key, tab: next });
    const [expanded, setExpanded] = useState(false);
    const [copied, setCopied] = useState(false);
    const frame = useRef<HTMLIFrameElement>(null);
    const Icon = ARTIFACT_ICONS[artifact.type];
    const document = useMemo(() => artifact.complete ? sandboxDocument(artifact) : null, [artifact]);
    const [run, setRun] = useState<{ document: string | null; status: "ready" | "error"; detail: string } | null>(null);
    const state = run?.document === document && run ? run : { status: "loading" as const, detail: "" };
    const documentRef = useRef(document);
    useEffect(() => { documentRef.current = document; }, [document]);

    useEffect(() => {
        const receive = (event: MessageEvent) => {
            // Only messages from this artifact's own sandbox frame are trusted.
            if (event.source !== frame.current?.contentWindow || event.data?.source !== "corten-artifact") return;
            const current = documentRef.current;
            if (event.data.type === "error") setRun({ document: current, status: "error", detail: String(event.data.detail || "Unknown error").slice(0, 600) });
            else if (event.data.type === "ready") setRun(previous => previous?.document === current && previous.status === "error" ? previous : { document: current, status: "ready", detail: "" });
        };
        window.addEventListener("message", receive);
        return () => window.removeEventListener("message", receive);
    }, []);
    useEffect(() => {
        const key = (event: KeyboardEvent) => { if (event.key === "Escape") { if (expanded) setExpanded(false); else onClose(); } };
        window.addEventListener("keydown", key);
        return () => window.removeEventListener("keydown", key);
    }, [expanded, onClose]);

    const copy = async () => {
        try { await navigator.clipboard.writeText(artifact.content); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch { /* Code remains selectable. */ }
    };
    const download = () => {
        const url = URL.createObjectURL(new Blob([artifact.content], { type: "text/plain;charset=utf-8" }));
        const link = window.document.createElement("a");
        link.href = url;
        link.download = artifactFilename(artifact);
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    };

    return (
        <aside className={`cx-panel ${expanded ? "cx-panel--expanded" : ""}`} aria-label={`Artifact: ${artifact.title}`}>
            <header className="cx-panel-header">
                <span className="cx-panel-icon" aria-hidden="true"><Icon size={16} /></span>
                <div className="cx-panel-title">
                    <h2>{artifact.title}</h2>
                    <span>{ARTIFACT_LABELS[artifact.type]}{!artifact.complete && " · Building…"}</span>
                </div>
                {versions.length > 1 && (
                    <div className="cx-versions" aria-label="Versions">
                        <button type="button" className="sx-icon-btn" aria-label="Previous version" disabled={index === 0} onClick={() => onIndex(index - 1)}><ChevronLeft size={14} /></button>
                        <span>v{index + 1} of {versions.length}</span>
                        <button type="button" className="sx-icon-btn" aria-label="Next version" disabled={index >= versions.length - 1} onClick={() => onIndex(index + 1)}><ChevronRight size={14} /></button>
                    </div>
                )}
                <div className="cx-panel-actions">
                    <button type="button" className="sx-icon-btn" aria-label={copied ? "Copied" : "Copy code"} title="Copy" onClick={() => void copy()}>{copied ? <Check size={15} /> : <Copy size={15} />}</button>
                    <button type="button" className="sx-icon-btn" aria-label="Download" title="Download" onClick={download} disabled={!artifact.complete}><Download size={15} /></button>
                    <button type="button" className="sx-icon-btn cx-panel-expand" aria-label={expanded ? "Exit full screen" : "Full screen"} title={expanded ? "Exit full screen" : "Full screen"}
                        onClick={() => setExpanded(!expanded)}>{expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button>
                    <button type="button" className="sx-icon-btn" aria-label="Close artifact" title="Close" onClick={onClose}><X size={16} /></button>
                </div>
            </header>
            {previewable && (
                <div className="cx-panel-tabs" role="tablist">
                    <button role="tab" aria-selected={tab === "preview"} className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}>Preview</button>
                    <button role="tab" aria-selected={tab === "code"} className={tab === "code" ? "active" : ""} onClick={() => setTab("code")}>Code</button>
                </div>
            )}
            {state.status === "error" && tab === "preview" && (
                <div className="cx-panel-error" role="alert">
                    <AlertTriangle size={15} aria-hidden="true" />
                    <span>This artifact hit an error: {state.detail}</span>
                    <button type="button" className="sx-btn sx-btn--secondary sx-btn--sm" disabled={fixDisabled}
                        onClick={() => onFix(`The artifact "${artifact.title}" shows this error when it runs: ${state.detail}\nFix the problem and return the complete updated artifact with the same title.`)}>
                        <Wand2 size={13} /> Ask Corten to fix
                    </button>
                </div>
            )}
            <div className="cx-panel-body">
                {tab === "preview" && previewable ? (
                    !artifact.complete ? (
                        <div className="cx-panel-building" role="status"><Loader2 size={20} className="sx-spin" /> Building {ARTIFACT_LABELS[artifact.type].toLowerCase()}… {artifact.content.split("\n").length} lines so far</div>
                    ) : artifact.type === "markdown" ? (
                        <div className="cx-panel-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact.content}</ReactMarkdown></div>
                    ) : (
                        <>
                            {state.status === "loading" && <div className="cx-panel-loading" aria-hidden="true"><Loader2 size={18} className="sx-spin" /></div>}
                            <iframe ref={frame} key={artifact.key} title={artifact.title} className="cx-panel-frame" srcDoc={document ?? ""}
                                sandbox={sandboxPermissions(artifact.type)} referrerPolicy="no-referrer"
                                onLoad={() => { if (artifact.type === "svg") setRun({ document, status: "ready", detail: "" }); }} />
                        </>
                    )
                ) : (
                    <SyntaxHighlighter language={artifact.type === "code" ? artifact.language || "text" : LANGUAGES[artifact.type]} style={oneDark}
                        showLineNumbers customStyle={{ margin: 0, minHeight: "100%", background: "#0b0d12", fontSize: 12.5 }} wrapLongLines>
                        {artifact.content}
                    </SyntaxHighlighter>
                )}
            </div>
        </aside>
    );
}
