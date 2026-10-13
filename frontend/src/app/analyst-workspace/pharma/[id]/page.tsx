import type { Metadata } from "next";
import { Suspense } from "react";
import PharmaRecordDetail from "@/components/analyst/PharmaRecordDetail";
import "@/styles/analyst-workspace.css";
import "@/styles/pharma-workspace.css";
import "@/styles/pharma-record.css";

export const metadata: Metadata = { title: "Pharma record | Corten AI" };
export default function PharmaRecordPage() {
    return <Suspense fallback={<div className="pi-detail-state" role="status">Loading record…</div>}><PharmaRecordDetail /></Suspense>;
}
