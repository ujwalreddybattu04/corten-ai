"use client";
import { useState } from "react";
import { Brain, ChevronDown, Download, FileText, FileSpreadsheet, Presentation, FileType2, Code2, LayoutDashboard, GitBranch, Image as ImageIcon, BookOpen, Globe, Loader2, ArrowUpRight } from "lucide-react";
import type { GeneratedFile, AttachmentRef } from "@/lib/chatApi";
import { formatBytes } from "@/lib/spacesApi";
import { ARTIFACT_LABELS, type Artifact, type ArtifactType } from "@/lib/artifacts";

/** Collapsible reasoning shown for Extended thinking answers. */
export function ThinkingPanel({ reasoning, active }: { reasoning: string; active: boolean }) {
    const [open, setOpen] = useState(false);
    if (!reasoning.trim()) return null;
    const words = reasoning.trim().split(/\s+/).length;
    return (
        <div className={`cx-thinking ${open ? "cx-thinking--open" : ""}`}>
            <button type="button" className="cx-thinking-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
                <Brain size={14} aria-hidden="true" className={active ? "cx-pulse" : ""} />
                <span>{active ? "Thinking…" : `Thought process · ${words.toLocaleString()} words`}</span>
                <ChevronDown size={14} aria-hidden="true" className="cx-thinking-chevron" />
            </button>
            {open && <div className="cx-thinking-body">{reasoning}</div>}
        </div>
    );
}

const FILE_ICONS = { docx: FileText, pdf: FileType2, xlsx: FileSpreadsheet, csv: FileSpreadsheet, pptx: Presentation };
const FILE_TINTS = { docx: "#2563eb", pdf: "#dc2626", xlsx: "#16a34a", csv: "#16a34a", pptx: "#ea580c" };

/** Download cards for files Corten created in an answer. */
export function FileCards({ files }: { files: GeneratedFile[] }) {
    if (!files.length) return null;
    return (
        <div className="cx-files">
            {files.map(file => {
                const Icon = FILE_ICONS[file.format] ?? FileText;
                const tint = FILE_TINTS[file.format] ?? "#64748b";
                return (
                    <a key={file.id} className="cx-file" href={file.url} download={file.name}>
                        <span className="cx-file-icon" style={{ background: tint + "1f", color: tint }} aria-hidden="true"><Icon size={20} /></span>
                        <span className="cx-file-text">
                            <span className="cx-file-name">{file.name}</span>
                            <span className="cx-file-meta">{file.label} · {formatBytes(file.size)}</span>
                        </span>
                        <span className="cx-file-download"><Download size={15} aria-hidden="true" /> Download</span>
                    </a>
                );
            })}
        </div>
    );
}

/** Thumbnails and file chips shown on a question that had attachments. */
export function SentAttachments({ items }: { items: AttachmentRef[] }) {
    if (!items?.length) return null;
    return (
        <div className="cx-sent">
            {items.map(item => item.kind === "image" ? (
                <a key={item.id} href={item.url} target="_blank" rel="noopener noreferrer" className="cx-sent-image" title={item.name}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={item.url} alt={item.name} loading="lazy" />
                </a>
            ) : (
                <a key={item.id} href={item.url} className="cx-sent-file" title={`Download ${item.name}`} download={item.name}>
                    <FileText size={14} aria-hidden="true" /><span>{item.name}</span>
                </a>
            ))}
        </div>
    );
}

export const ARTIFACT_ICONS: Record<ArtifactType, typeof Code2> = {
    react: LayoutDashboard, html: Globe, mermaid: GitBranch, svg: ImageIcon, markdown: BookOpen, code: Code2,
};

/** Inline card for an artifact; opens it in the side panel. */
export function ArtifactCard({ artifact, active, version, onOpen }: {
    artifact: Artifact; active: boolean; version?: number; onOpen: () => void;
}) {
    const Icon = ARTIFACT_ICONS[artifact.type];
    const lines = artifact.content.split("\n").length;
    return (
        <button type="button" className={`cx-artifact-card ${active ? "cx-artifact-card--active" : ""}`} onClick={onOpen}
            aria-label={`Open ${artifact.title}`}>
            <span className="cx-artifact-card-icon" aria-hidden="true"><Icon size={20} /></span>
            <span className="cx-artifact-card-text">
                <span className="cx-artifact-card-title">{artifact.title}</span>
                <span className="cx-artifact-card-meta">
                    {ARTIFACT_LABELS[artifact.type]}{version && version > 1 ? ` · Version ${version}` : ""}
                    {artifact.complete ? ` · ${lines.toLocaleString()} lines` : <> · <Loader2 size={11} className="sx-spin" aria-hidden="true" /> Building… {lines} lines</>}
                </span>
            </span>
            <span className="cx-artifact-card-open" aria-hidden="true">{artifact.complete ? <>Open <ArrowUpRight size={13} /></> : null}</span>
        </button>
    );
}

export { linkCitations } from "@/lib/citations";
