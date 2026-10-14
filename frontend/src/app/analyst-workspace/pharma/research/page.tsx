import type { Metadata } from "next";
import { Suspense } from "react";
import PharmaResearch from "@/components/analyst/PharmaResearch";
import "@/styles/analyst-workspace.css";
import "@/styles/pharma-workspace.css";
import "@/styles/pharma-record.css";
import "@/styles/pharma-research.css";

export const metadata: Metadata = { title: "Pharma research | Corten AI" };
export default function Page() {
    return <Suspense fallback={<div className="pi-detail-state" role="status">Loading research…</div>}><PharmaResearch /></Suspense>;
}
