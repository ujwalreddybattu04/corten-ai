"use client";

import { useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
    ChevronRight, BookOpen, Code, Lightbulb, GraduationCap,
    Beaker, PenTool, TrendingUp, Briefcase, Bookmark,
    FolderOpen, ArrowRight
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface SpaceTemplate {
    id: string;
    name: string;
    description: string;
    icon: string;
    color: string;
    instructions: string;
    category: string;
}

interface LocalSpace {
    id: string;
    name: string;
    description: string;
    icon: string;
    color: string;
    isPrivate: boolean;
    threadIds: string[];
    links: string[];
    instructions: string;
    createdAt: number;
    updatedAt: number;
}

const STORAGE_KEY = "corten_spaces";

const CATEGORIES = ["All", "Research", "Education", "Development", "Life"];

// ── Templates ───────────────────────────────────────────────────────────────

const TEMPLATES: SpaceTemplate[] = [
    // Research
    {
        id: "tpl_research",
        name: "Research Assistant",
        description: "Get deep, cited, in-depth answers with academic rigor on any research topic.",
        icon: "book",
        color: "#3b82f6",
        category: "Research",
        instructions: "Always provide detailed, well-sourced answers. Cite academic papers and reputable sources when possible. Structure responses with clear sections and headings. Prioritize peer-reviewed sources over blogs. Include a brief summary at the top of long answers.",
    },
    {
        id: "tpl_patent",
        name: "Patent Researcher",
        description: "Search, summarize, and analyze patents and prior art by topic, company, or inventor.",
        icon: "beaker",
        color: "#14b8a6",
        category: "Research",
        instructions: "When analyzing patents, provide the patent number, title, filing date, and assignee. Summarize the key claims and innovations. Compare with related prior art. Highlight potential applications and limitations. Use structured format with clear sections.",
    },
    {
        id: "tpl_data",
        name: "Data Analyst",
        description: "Analyze data trends, interpret statistics, and generate insights from any dataset.",
        icon: "trending",
        color: "#f97316",
        category: "Research",
        instructions: "When analyzing data, always explain methodology and assumptions. Use clear statistical language but explain terms for non-experts. Provide confidence levels where applicable. Suggest visualizations that would best represent the data. Highlight actionable insights, not just observations.",
    },
    // Education
    {
        id: "tpl_study",
        name: "Study Guide Generator",
        description: "Convert notes, slides, or textbooks into comprehensive and organized study guides.",
        icon: "graduation",
        color: "#22c55e",
        category: "Education",
        instructions: "Create well-organized study guides with clear headings, bullet points, and key definitions. Include mnemonics and memory aids where helpful. Add practice questions at the end of each section. Highlight the most exam-relevant material. Use simple language to explain complex concepts.",
    },
    {
        id: "tpl_tutor",
        name: "Tutor Me",
        description: "Step-by-step help learning a concept, solving a problem, or mastering a difficult topic.",
        icon: "lightbulb",
        color: "#eab308",
        category: "Education",
        instructions: "Act as a patient, encouraging tutor. Break down complex topics into small, digestible steps. Ask guiding questions rather than giving answers directly. Use analogies and real-world examples to explain abstract concepts. Check understanding at each step before moving on. Adapt explanations to the student's level.",
    },
    {
        id: "tpl_essay",
        name: "Essay Grader",
        description: "Upload your essay and receive detailed feedback based on rubric and writing quality.",
        icon: "pen",
        color: "#f43f5e",
        category: "Education",
        instructions: "Grade essays on these criteria: thesis clarity, argument structure, evidence quality, writing mechanics, and originality. Provide a score for each criterion. Give specific, line-level feedback with suggestions for improvement. Highlight both strengths and weaknesses. End with 3 concrete action items for the next draft.",
    },
    // Development
    {
        id: "tpl_code",
        name: "Code Helper",
        description: "Programming help with clear explanations, working code examples, and debugging assistance.",
        icon: "code",
        color: "#6366f1",
        category: "Development",
        instructions: "Always include working code examples with proper syntax. Explain code step-by-step. When debugging, identify the root cause first before suggesting fixes. Use modern best practices and idiomatic syntax. Mention time and space complexity for algorithms. Include error handling in examples.",
    },
    // Life
    {
        id: "tpl_writing",
        name: "Writing Coach",
        description: "Improve your writing with constructive feedback, editing, and creative brainstorming.",
        icon: "pen",
        color: "#ec4899",
        category: "Life",
        instructions: "Provide constructive, specific feedback on writing — not just praise. Suggest concrete improvements for clarity, tone, and structure. When brainstorming, offer at least 3 creative angles. Explain why each suggestion improves the text. Adapt tone advice to the intended audience.",
    },
    {
        id: "tpl_trip",
        name: "Trip Planner Pro",
        description: "Plan your trip with personalized itineraries, budgets, and local recommendations.",
        icon: "briefcase",
        color: "#8b5cf6",
        category: "Life",
        instructions: "When planning trips, ask about budget, travel dates, interests, and group size. Create day-by-day itineraries with morning/afternoon/evening blocks. Include estimated costs, travel times between locations, and booking tips. Recommend local restaurants and hidden gems over tourist traps. Mention seasonal considerations and local customs.",
    },
];

function getIconComponent(key: string, size = 22) {
    const map: Record<string, React.ReactNode> = {
        bookmark: <Bookmark size={size} />,
        folder: <FolderOpen size={size} />,
        book: <BookOpen size={size} />,
        briefcase: <Briefcase size={size} />,
        code: <Code size={size} />,
        lightbulb: <Lightbulb size={size} />,
        graduation: <GraduationCap size={size} />,
        beaker: <Beaker size={size} />,
        pen: <PenTool size={size} />,
        trending: <TrendingUp size={size} />,
    };
    return map[key] || <Bookmark size={size} />;
}

function generateId() {
    return "sp_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TemplatesPage() {
    const router = useRouter();
    const [activeCategory, setActiveCategory] = useState("All");

    const filtered = useMemo(() => {
        if (activeCategory === "All") return TEMPLATES;
        return TEMPLATES.filter(t => t.category === activeCategory);
    }, [activeCategory]);

    const handleUseTemplate = useCallback((tpl: SpaceTemplate) => {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            const spaces: LocalSpace[] = raw ? JSON.parse(raw) : [];
            const newSpace: LocalSpace = {
                id: generateId(),
                name: tpl.name,
                description: tpl.description,
                icon: tpl.icon,
                color: tpl.color,
                isPrivate: true,
                threadIds: [],
                links: [],
                instructions: tpl.instructions,
                createdAt: Date.now(),
                updatedAt: Date.now(),
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify([newSpace, ...spaces]));
            router.push(`/spaces/${newSpace.id}`);
        } catch { /* ignore */ }
    }, [router]);

    return (
        <div className="tpl-page">
            {/* Breadcrumb */}
            <div className="tpl-topbar">
                <div className="tpl-breadcrumb">
                    <Link href="/spaces" className="tpl-breadcrumb-link">Spaces</Link>
                    <ChevronRight size={13} className="tpl-breadcrumb-sep" />
                    <span className="tpl-breadcrumb-current">Templates</span>
                </div>
            </div>

            {/* Header + Tabs */}
            <div className="tpl-hero">
                <div className="tpl-hero-inner">
                    <h1 className="tpl-title">Templates</h1>
                    <p className="tpl-subtitle">Get started quickly with pre-configured spaces. Each template comes with custom instructions tailored for a specific use case.</p>

                    <div className="tpl-tabs">
                        {CATEGORIES.map(cat => (
                            <button
                                key={cat}
                                className={`tpl-tab ${activeCategory === cat ? "active" : ""}`}
                                onClick={() => setActiveCategory(cat)}
                            >
                                {cat}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Grid */}
            <div className="tpl-body">
                <div className="tpl-grid">
                    {filtered.map(tpl => (
                        <button
                            key={tpl.id}
                            className="tpl-card"
                            onClick={() => handleUseTemplate(tpl)}
                        >
                            <div className="tpl-card-icon" style={{ background: tpl.color + "15", color: tpl.color }}>
                                {getIconComponent(tpl.icon, 22)}
                            </div>
                            <div className="tpl-card-body">
                                <h3 className="tpl-card-name">{tpl.name}</h3>
                                <p className="tpl-card-desc">{tpl.description}</p>
                            </div>
                            <div className="tpl-card-footer">
                                <span className="tpl-card-cat">{tpl.category}</span>
                                <span className="tpl-card-cta">
                                    Use <ArrowRight size={11} />
                                </span>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
