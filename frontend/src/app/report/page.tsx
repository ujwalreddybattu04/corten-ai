"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useReport, ReportSection, ReportStep } from "@/hooks/useReport";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
    FileText, Download, Loader2, CheckCircle2, Circle,
    Clock, BookOpen, X, ArrowLeft, AlertCircle, RotateCcw,
} from "lucide-react";

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ReportPage() {
    return <Suspense fallback={<div className="rpt-page" role="status">Loading report…</div>}><ReportContent /></Suspense>;
}

function ReportContent() {
    const [downloadError, setDownloadError] = useState("");
    const [downloading, setDownloading] = useState(false);
    const searchParams = useSearchParams();
    const topic = searchParams.get("topic") || "";
    const focus = searchParams.get("focus") || "all";

    const {
        isGenerating,
        title,
        subtitle,
        steps,
        sections,
        sources,
        statusMessage,
        result,
        error,
        currentSection,
        totalSections,
        generateReport,
        cancelReport,
    } = useReport();

    // Auto-start on mount
    useEffect(() => {
        if (!topic) return;
        void generateReport(topic, focus);
        return cancelReport;
    }, [topic, focus, generateReport, cancelReport]);

    const previewRef = useRef<HTMLDivElement>(null);
    const stepsEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll preview as new content appears
    useEffect(() => {
        if (previewRef.current) {
            previewRef.current.scrollTop = previewRef.current.scrollHeight;
        }
    }, [sections]);

    // Auto-scroll steps panel to keep latest step visible
    useEffect(() => {
        if (stepsEndRef.current) {
            stepsEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
        }
    }, [steps]);

    const completedSections = sections.filter(s => s.status === "complete").length;
    const progress = totalSections > 0 ? Math.round((completedSections / totalSections) * 100) : 0;

    const handleDownload = async () => {
        if (!result) return;
        setDownloading(true); setDownloadError("");
        try {
            if (!/^\/api\/v1\/report\/download\/[a-f0-9]{32}$/.test(result.downloadUrl)) throw new Error("Invalid report download link.");
            const response = await api.response(result.downloadUrl, { signal: AbortSignal.timeout(30000) });
            if (!response.headers.get("Content-Type")?.startsWith("application/pdf")) throw new Error("The report download is unavailable. Please retry.");
            const blob = await response.blob(), url = URL.createObjectURL(blob);
            const link = document.createElement("a"); link.href = url; link.download = result.filename; link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { setDownloadError(error instanceof Error ? error.message : "Unable to download. Please retry."); }
        finally { setDownloading(false); }
    };

    return (
        <div className="rpt-page">
            {/* ── Left Panel: Progress ── */}
            <div className="rpt-left">
                {/* Header */}
                <div className="rpt-left-header">
                <Link href="/" className="rpt-back-btn">
                    <ArrowLeft size={16} />
                </Link>
                    <div className="rpt-header-info">
                        <div className="rpt-header-badge">
                            <FileText size={14} />
                            <span>Report Generation</span>
                        </div>
                        <h1 className="rpt-topic">{topic}</h1>
                    </div>
                </div>

                {/* Progress Bar */}
                {isGenerating && (
                    <div className="rpt-progress-bar-wrapper">
                        <div className="rpt-progress-bar">
                            <div className="rpt-progress-fill" style={{ width: `${progress}%` }} />
                        </div>
                        <span className="rpt-progress-text">
                            {progress}% — {statusMessage}
                        </span>
                    </div>
                )}

                {/* Steps Timeline — Connected Line Design */}
                <div className="rpt-timeline">
                    {steps.map((step, i) => (
                        <StepItem
                            key={step.id}
                            step={step}
                            index={i}
                            isLast={i === steps.length - 1 && !isGenerating}
                        />
                    ))}
                    {isGenerating && steps.length > 0 && (
                        <div className="rpt-tl-item active" style={{ animationDelay: "0ms" }}>
                            <div className="rpt-tl-connector">
                                <div className="rpt-tl-line" />
                                <div className="rpt-tl-node active">
                                    <Loader2 size={12} className="rpt-spin" />
                                </div>
                            </div>
                            <div className="rpt-tl-content">
                                <span className="rpt-tl-label shimmer-text">{statusMessage}</span>
                            </div>
                        </div>
                    )}
                    <div ref={stepsEndRef} />
                </div>

                {/* Error */}
                {error && (
                    <>
                        <div className="rpt-error" role="alert">
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                        <button type="button" className="rpt-cancel-btn" onClick={() => void generateReport(topic, focus)}>
                            <RotateCcw size={14} /> Retry report
                        </button>
                    </>
                )}

                {/* Result Card */}
                {result && (
                    <div className="rpt-result-card">
                        <div className="rpt-result-top">
                            <div className="rpt-result-icon">
                                <FileText size={20} />
                            </div>
                            <div className="rpt-result-info">
                                <h3 className="rpt-result-title">{result.title}</h3>
                                <p className="rpt-result-subtitle">{result.subtitle || "Generated report"}</p>
                            </div>
                        </div>
                        <div className="rpt-result-stats">
                            <div className="rpt-result-stat">
                                <span className="rpt-result-stat-value">{result.pages}</span>
                                <span className="rpt-result-stat-label">Pages</span>
                            </div>
                            <div className="rpt-result-stat">
                                <span className="rpt-result-stat-value">{formatFileSize(result.fileSize)}</span>
                                <span className="rpt-result-stat-label">Size</span>
                            </div>
                            <div className="rpt-result-stat">
                                <span className="rpt-result-stat-value">{result.sourcesCount}</span>
                                <span className="rpt-result-stat-label">Sources</span>
                            </div>
                            <div className="rpt-result-stat">
                                <span className="rpt-result-stat-value">{result.generationTime}s</span>
                                <span className="rpt-result-stat-label">Time</span>
                            </div>
                        </div>
                        <button className="rpt-download-btn" onClick={() => void handleDownload()} disabled={downloading}>
                            <Download size={16} />
                            {downloading ? "Downloading…" : "Download PDF"}
                        </button>
                        {downloadError && <p role="alert">{downloadError}</p>}
                    </div>
                )}

                {/* Sources */}
                {sources.length > 0 && (
                    <div className="rpt-sources-section">
                        <div className="rpt-sources-header">
                            <BookOpen size={14} />
                            <span>{sources.length} sources</span>
                        </div>
                        <div className="rpt-sources-list">
                            {sources.slice(0, 8).map((src, i) => (
                                <a
                                    key={i}
                                    href={src.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="rpt-source-item"
                                >
                                    <img
                                        src={src.favicon}
                                        alt=""
                                        className="rpt-source-favicon"
                                        width={16}
                                        height={16}
                                    />
                                    <span className="rpt-source-title">{src.title}</span>
                                </a>
                            ))}
                        </div>
                    </div>
                )}

                {/* Cancel button */}
                {isGenerating && (
                    <button className="rpt-cancel-btn" onClick={cancelReport}>
                        <X size={14} />
                        Cancel
                    </button>
                )}
            </div>

            {/* ── Right Panel: Report Preview ── */}
            <div className="rpt-right" ref={previewRef}>
                {sections.length === 0 && !error ? (
                    <div className="rpt-preview-empty">
                        <div className="rpt-preview-empty-icon">
                            <FileText size={40} strokeWidth={1} />
                        </div>
                        <span className="rpt-preview-empty-text">
                            {isGenerating ? "Researching and planning..." : "Report preview will appear here"}
                        </span>
                        {isGenerating && (
                            <div className="rpt-preview-loader">
                                <Loader2 size={20} className="rpt-spin" />
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="rpt-preview-content">
                        {/* Report Header */}
                        {title && (
                            <div className="rpt-preview-header">
                                <div className="rpt-preview-brand">CORTEN AI REPORT</div>
                                <h1 className="rpt-preview-title">{title}</h1>
                                {subtitle && <p className="rpt-preview-subtitle">{subtitle}</p>}
                                <div className="rpt-preview-meta-line">
                                    <Clock size={12} />
                                    <span>{new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}</span>
                                    <span className="rpt-dot" />
                                    <span>{sources.length} sources</span>
                                </div>
                            </div>
                        )}

                        {/* Sections */}
                        {sections.map((section) => (
                            <SectionPreview key={section.index} section={section} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function StepItem({ step, index, isLast }: { step: ReportStep; index: number; isLast: boolean }) {
    return (
        <div
            className={`rpt-tl-item ${step.status}`}
            style={{ animationDelay: `${index * 60}ms` }}
        >
            <div className="rpt-tl-connector">
                {!isLast && <div className={`rpt-tl-line ${step.status}`} />}
                <div className={`rpt-tl-node ${step.status}`}>
                    {step.status === "complete" ? (
                        <CheckCircle2 size={14} />
                    ) : step.status === "active" ? (
                        <Loader2 size={12} className="rpt-spin" />
                    ) : (
                        <Circle size={12} />
                    )}
                </div>
            </div>
            <div className="rpt-tl-content">
                <span className={`rpt-tl-label ${step.status === "active" ? "shimmer-text" : ""}`}>
                    {step.step}
                </span>
                <span className="rpt-tl-detail">{step.detail}</span>
            </div>
        </div>
    );
}

function SectionPreview({ section }: { section: ReportSection }) {
    return (
        <div className={`rpt-section ${section.status}`}>
            <div className="rpt-section-header">
                <div className="rpt-section-status-icon">
                    {section.status === "complete" ? (
                        <CheckCircle2 size={14} />
                    ) : section.status === "writing" ? (
                        <Loader2 size={14} className="rpt-spin" />
                    ) : (
                        <Circle size={14} />
                    )}
                </div>
                <h2 className={`rpt-section-title ${section.status === "writing" && !section.content ? "shimmer-text" : ""}`}>
                    {section.title}
                </h2>
            </div>
            {section.content ? (
                <div className="rpt-section-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {section.content}
                    </ReactMarkdown>
                    {section.status === "writing" && (
                        <span className="rpt-typing-cursor" />
                    )}
                </div>
            ) : section.status === "writing" ? (
                <div className="rpt-section-skeleton">
                    <div className="rpt-skeleton-line w80" />
                    <div className="rpt-skeleton-line w60" />
                    <div className="rpt-skeleton-line w90" />
                    <div className="rpt-skeleton-line w40" />
                </div>
            ) : null}
        </div>
    );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
