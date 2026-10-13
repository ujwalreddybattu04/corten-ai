"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { SPACE_TEMPLATES, TEMPLATE_CATEGORIES, type TemplateCategory } from "@/lib/spaceTemplates";
import TemplateGrid from "@/components/spaces/TemplateGrid";

export default function TemplatesPage() {
    const [category, setCategory] = useState<TemplateCategory | "All">("All");
    const templates = useMemo(() => category === "All" ? SPACE_TEMPLATES : SPACE_TEMPLATES.filter(item => item.category === category), [category]);
    return (
        <div className="sv-page">
            <div className="sv-page-inner">
                <Link href="/spaces" className="sv-back"><ArrowLeft size={15} /> Spaces</Link>
                <header className="sv-home-head">
                    <div>
                        <h1>Templates</h1>
                        <p>Each template gives its Space an agent with the tools for the job, such as live market data, clinical trials, research papers and charts, plus instructions you can change at any time.</p>
                    </div>
                </header>
                <div className="sv-toolbar">
                    <div className="sv-segmented" role="tablist" aria-label="Template categories">
                        {(["All", ...TEMPLATE_CATEGORIES] as const).map(item => (
                            <button key={item} role="tab" aria-selected={category === item} className={category === item ? "active" : ""}
                                onClick={() => setCategory(item)}>{item}</button>
                        ))}
                    </div>
                </div>
                <TemplateGrid templates={templates} />
            </div>
        </div>
    );
}
