import type { Metadata } from 'next';
import { Suspense } from 'react';
import PharmaDeepResearch from '@/components/analyst/PharmaDeepResearch';
import '@/styles/analyst-workspace.css';
import '@/styles/pharma-workspace.css';
import '@/styles/pharma-record.css';
import '@/styles/pharma-research.css';
import '@/styles/pharma-deep.css';
export const metadata: Metadata = { title: 'Pharma deep research | Corten AI' };
export default function Page() { return <Suspense fallback={<div className="pi-detail-state" role="status">Loading Deep research…</div>}><PharmaDeepResearch /></Suspense>; }
