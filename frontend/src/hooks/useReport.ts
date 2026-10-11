"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { readReportStream } from "@/lib/reportStream";

// ── Types ────────────────────────────────────────────────────────────────────

export interface ReportSection {
    index: number;
    title: string;
    content: string;
    status: "pending" | "writing" | "complete";
}

export interface ReportSource {
    url: string;
    title: string;
    domain: string;
    favicon: string;
    snippet: string;
    citationIndex: number;
}

export interface ReportStep {
    id: string;
    step: string;
    detail: string;
    status: "complete" | "active" | "pending";
    timestamp: number;
}

export interface ReportResult {
    downloadUrl: string;
    filename: string;
    pages: number;
    title: string;
    subtitle: string;
    fileSize: number;
    sourcesCount: number;
    generationTime: number;
}

interface ReportState {
    isGenerating: boolean;
    reportId: string | null;
    title: string;
    subtitle: string;
    steps: ReportStep[];
    sections: ReportSection[];
    sources: ReportSource[];
    statusMessage: string;
    result: ReportResult | null;
    error: string | null;
    currentSection: number;
    totalSections: number;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useReport() {
    const [state, setState] = useState<ReportState>({
        isGenerating: false,
        reportId: null,
        title: "",
        subtitle: "",
        steps: [],
        sections: [],
        sources: [],
        statusMessage: "",
        result: null,
        error: null,
        currentSection: 0,
        totalSections: 0,
    });

    const abortRef = useRef<AbortController | null>(null);
    const generationRef = useRef(0);
    useEffect(() => () => {
        generationRef.current++;
        abortRef.current?.abort();
    }, []);
    const stepIdCounter = useRef(0);

    const addStep = useCallback((step: string, detail: string, status: "complete" | "active" = "active") => {
        const id = `step_${stepIdCounter.current++}`;
        setState(prev => {
            // Mark previous active steps as complete
            const updatedSteps = prev.steps.map(s =>
                s.status === "active" ? { ...s, status: "complete" as const } : s
            );
            return {
                ...prev,
                steps: [...updatedSteps, { id, step, detail, status, timestamp: Date.now() }],
            };
        });
    }, []);

    const generateReport = useCallback(async (topic: string, focusMode: string = "all") => {
        // Abort any in-flight request
        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        const generation = ++generationRef.current;
        const isCurrent = () => generation === generationRef.current && !controller.signal.aborted;

        stepIdCounter.current = 0;

        setState({
            isGenerating: true,
            reportId: null,
            title: "",
            subtitle: "",
            steps: [],
            sections: [],
            sources: [],
            statusMessage: "Starting report generation...",
            result: null,
            error: null,
            currentSection: 0,
            totalSections: 0,
        });

        try {
            const response = await fetch("/api/v1/report/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic, focus_mode: focusMode }),
                signal: controller.signal,
            });

            await readReportStream(response, event => {
                if (isCurrent()) handleEvent(event, addStep, setState);
            });
            if (isCurrent()) setState(prev => ({ ...prev, isGenerating: false }));
        } catch (err: unknown) {
            if (!isCurrent()) return;
            setState(prev => ({
                ...prev,
                isGenerating: false,
                result: null,
                error: err instanceof Error ? err.message : "Report generation failed",
            }));
        }
    }, [addStep]);

    const cancelReport = useCallback(() => {
        if (abortRef.current) {
            generationRef.current++;
            abortRef.current.abort();
            setState(prev => ({ ...prev, isGenerating: false, statusMessage: "Cancelled" }));
        }
    }, []);

    return {
        ...state,
        generateReport,
        cancelReport,
    };
}

// ── Event Handler ────────────────────────────────────────────────────────────

function handleEvent(
    json: any,
    addStep: (step: string, detail: string, status?: "complete" | "active") => void,
    setState: React.Dispatch<React.SetStateAction<ReportState>>,
) {
    switch (json.type) {
        case "report_start":
            setState(prev => ({ ...prev, reportId: json.report_id }));
            break;

        case "report_status":
            setState(prev => ({ ...prev, statusMessage: json.content }));
            break;

        case "research_step":
            addStep(json.step, json.detail);
            break;

        case "sources":
            setState(prev => ({ ...prev, sources: json.sources || json.items || [] }));
            break;

        case "report_outline":
            setState(prev => {
                const sections: ReportSection[] = [
                    { index: 0, title: "Executive Summary", content: "", status: "pending" },
                    ...(json.sections || []).map((s: any, i: number) => ({
                        index: i + 1,
                        title: s.title,
                        content: "",
                        status: "pending" as const,
                    })),
                ];
                return {
                    ...prev,
                    title: json.title || "",
                    subtitle: json.subtitle || "",
                    sections,
                    totalSections: sections.length,
                };
            });
            addStep("Outline", `${(json.sections || []).length} sections planned`, "complete");
            break;

        case "section_start":
            setState(prev => {
                const sections = prev.sections.map(s =>
                    s.index === json.index ? { ...s, status: "writing" as const } : s
                );
                return { ...prev, sections, currentSection: json.index };
            });
            addStep("Writing", json.title);
            break;

        case "section_content":
            setState(prev => {
                const sections = prev.sections.map(s =>
                    s.index === json.index ? { ...s, content: s.content + json.chunk } : s
                );
                return { ...prev, sections };
            });
            break;

        case "section_complete":
            setState(prev => {
                const sections = prev.sections.map(s =>
                    s.index === json.index ? { ...s, status: "complete" as const } : s
                );
                return { ...prev, sections };
            });
            break;

        case "report_generating_pdf":
            addStep("Formatting", json.step);
            break;

        case "report_complete":
            setState(prev => ({
                ...prev,
                statusMessage: "Report complete!",
                result: {
                    downloadUrl: json.download_url,
                    filename: json.filename,
                    pages: json.pages,
                    title: json.title,
                    subtitle: json.subtitle,
                    fileSize: json.file_size,
                    sourcesCount: json.sources_count,
                    generationTime: json.generation_time,
                },
            }));
            // Mark all steps complete
            setState(prev => ({
                ...prev,
                steps: prev.steps.map(s => ({ ...s, status: "complete" as const })),
            }));
            break;

        case "error":
            setState(prev => ({
                ...prev,
                isGenerating: false,
                error: json.message || "An error occurred",
            }));
            break;

        case "done":
            setState(prev => ({ ...prev, isGenerating: false }));
            break;
    }
}
