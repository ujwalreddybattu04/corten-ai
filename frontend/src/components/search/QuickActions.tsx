"use client";

import { useState, useMemo, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

// ─── Suggestion pool ────────────────────────────────────────────────────────
// Each category has 8+ prompts; 4 are randomly selected per page load so the
// page feels fresh and dynamic, not hardcoded.
const CATEGORIES = [
    {
        id: "summarize",
        label: "Summarize",
        icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
        ),
        pool: [
            "Summarize the latest breakthroughs in AI research",
            "Summarize the key events in the Russia-Ukraine conflict",
            "Give me a TL;DR of climate change in 2025",
            "Summarize how transformer models work",
            "Summarize the current state of quantum computing",
            "What happened in the global economy this week?",
            "Summarize the history of the internet in 5 points",
            "Summarize how CRISPR gene editing works",
        ],
    },
    {
        id: "analyze",
        label: "Analyze",
        icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
            </svg>
        ),
        pool: [
            "Analyze the pros and cons of electric vehicles",
            "Analyze the impact of AI on the job market",
            "Analyze India's GDP growth over the last decade",
            "Analyze why startups fail in their first year",
            "Analyze the risks and opportunities in cryptocurrency",
            "What are the biggest risks in large language models?",
            "Analyze the causes of the 2008 financial crisis",
            "Analyze the competitive landscape of cloud computing",
        ],
    },
    {
        id: "learn",
        label: "Learn",
        icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </svg>
        ),
        pool: [
            "Explain quantum computing in simple terms",
            "How does the human immune system work?",
            "Teach me how neural networks learn",
            "How does blockchain actually work?",
            "What is the theory of relativity in plain English?",
            "Explain how the stock market works for beginners",
            "How do vaccines train the immune system?",
            "What is machine learning and how do I get started?",
        ],
    },
    {
        id: "discover",
        label: "Discover",
        icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <polygon points="10 8 16 12 10 16 10 8" />
            </svg>
        ),
        pool: [
            "What are the most surprising facts about the human brain?",
            "What is happening in space exploration right now?",
            "What are the most innovative companies in 2025?",
            "What are the biggest unsolved problems in mathematics?",
            "Discover the most interesting scientific findings of 2024",
            "What technologies will change the world in 10 years?",
            "What are the top emerging fields in computer science?",
            "What are the most fascinating deep sea discoveries?",
        ],
    },
    {
        id: "write",
        label: "Write",
        icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
        ),
        pool: [
            "Write a professional bio for LinkedIn",
            "Write a cover letter for a software engineer role",
            "Help me write an email asking for a raise",
            "Write a business proposal outline",
            "Write a 30-second elevator pitch for my startup",
            "Help me write a compelling product description",
            "Write an apology email to a client professionally",
            "Help me write a research paper introduction",
        ],
    },
    {
        id: "compare",
        label: "Compare",
        icon: (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 20V10" />
                <path d="M12 20V4" />
                <path d="M6 20v-6" />
            </svg>
        ),
        pool: [
            "Compare Python vs JavaScript for backend development",
            "Compare OpenAI GPT-4 vs Google Gemini",
            "Compare React vs Vue for building web apps",
            "Compare AWS vs Google Cloud vs Azure",
            "Compare electric cars: Tesla vs Rivian vs Lucid",
            "Compare capitalism vs socialism: key differences",
            "Compare the Roman Empire and the Mongol Empire",
            "Compare iOS vs Android: which is better in 2025?",
        ],
    },
];

// Fisher-Yates shuffle then pick N
function pickRandom<T>(arr: T[], n: number): T[] {
    const copy = [...arr];
    for (let i = copy.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy.slice(0, n);
}

// Animation variants — ease arrays cast as const to satisfy Framer Motion's BezierDefinition type
const SPRING_EASE = [0.16, 1, 0.3, 1] as const;

const panelVariants = {
    hidden: { opacity: 0, y: -6, height: 0 },
    visible: {
        opacity: 1,
        y: 0,
        height: "auto",
        transition: { duration: 0.22, ease: SPRING_EASE },
    },
    exit: {
        opacity: 0,
        y: -4,
        height: 0,
        transition: { duration: 0.16, ease: "easeIn" as const },
    },
};

const itemVariants = {
    hidden: { opacity: 0, x: -8 },
    visible: (i: number) => ({
        opacity: 1,
        x: 0,
        transition: { delay: i * 0.045, duration: 0.2, ease: SPRING_EASE },
    }),
};

interface QuickActionsProps {
    onAction?: (prompt: string) => void;
}

export default function QuickActions({ onAction }: QuickActionsProps) {
    const router = useRouter();
    const [activeId, setActiveId] = useState<string | null>(null);

    // Randomly pick 4 from each category's pool — refreshes every page load
    const categories = useMemo(
        () => CATEGORIES.map((cat) => ({ ...cat, suggestions: pickRandom(cat.pool, 4) })),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        []
    );

    const handleChipClick = useCallback((id: string) => {
        setActiveId((prev) => (prev === id ? null : id));
    }, []);

    const handleSuggestionClick = useCallback(
        (prompt: string) => {
            if (onAction) {
                onAction(prompt);
            } else {
                router.push(`/search?q=${encodeURIComponent(prompt)}&focus=all`);
            }
            setActiveId(null);
        },
        [onAction, router]
    );

    const activeCategory = categories.find((c) => c.id === activeId);

    return (
        <div className="qa-wrapper">
            {/* Chip row */}
            <div className="qa-chips">
                {categories.map((cat) => (
                    <button
                        key={cat.id}
                        className={`qa-chip ${activeId === cat.id ? "qa-chip--active" : ""}`}
                        onClick={() => handleChipClick(cat.id)}
                        aria-expanded={activeId === cat.id}
                        aria-controls={`qa-panel-${cat.id}`}
                    >
                        <span className="qa-chip-icon" aria-hidden="true">{cat.icon}</span>
                        <span className="qa-chip-label">{cat.label}</span>
                        <span
                            className={`qa-chip-arrow ${activeId === cat.id ? "qa-chip-arrow--open" : ""}`}
                            aria-hidden="true"
                        >
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="6 9 12 15 18 9" />
                            </svg>
                        </span>
                    </button>
                ))}
            </div>

            {/* Expanded suggestions panel */}
            <AnimatePresence mode="wait">
                {activeCategory && (
                    <motion.div
                        key={activeCategory.id}
                        id={`qa-panel-${activeCategory.id}`}
                        className="qa-panel"
                        variants={panelVariants}
                        initial="hidden"
                        animate="visible"
                        exit="exit"
                        style={{ overflow: "hidden" }}
                    >
                        <div className="qa-panel-inner">
                            {activeCategory.suggestions.map((suggestion, i) => (
                                <motion.button
                                    key={suggestion}
                                    className="qa-suggestion"
                                    custom={i}
                                    variants={itemVariants}
                                    initial="hidden"
                                    animate="visible"
                                    onClick={() => handleSuggestionClick(suggestion)}
                                    whileHover={{ x: 3 }}
                                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                                >
                                    <span className="qa-suggestion-text">{suggestion}</span>
                                    <span className="qa-suggestion-arrow" aria-hidden="true">
                                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                            <line x1="5" y1="12" x2="19" y2="12" />
                                            <polyline points="12 5 19 12 12 19" />
                                        </svg>
                                    </span>
                                </motion.button>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
