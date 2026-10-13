"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowUpRight, LoaderCircle } from "lucide-react";
import { PHARMA_SOURCE_LABELS, validPharmaItem, type PharmaItem } from "@/lib/pharmaFeed";
import { pharmaRecordPath } from "@/lib/pharmaRecord";

type Timeline = { drug: { id: string; name: string; aliases: string[]; evidence_url: string }; items: PharmaItem[]; next_cursor: string | null };
export default function PharmaDrugTimeline() {
  const { id } = useParams<{ id: string }>();
  const [snapshot, setData] = useState<Timeline | null>(null);
  const data = snapshot?.drug.id === id ? snapshot : null;
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [material, setMaterial] = useState(false);
  const request = useRef<AbortController | null>(null);
  const load = useCallback(async (cursor?: string | null) => {
    if (request.current) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/v1/pharma/drugs/${encodeURIComponent(id)}/timeline${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 404 ? "This verified drug identity was not found." : "The drug timeline is temporarily unavailable.");
      const value = await response.json() as Timeline;
      const url = new URL(value.drug.evidence_url);
      if (value.drug.id !== id || typeof value.drug.name !== "string" || value.drug.name.length > 240
        || url.protocol !== "https:" || url.username || url.password || !Array.isArray(value.drug.aliases) || value.drug.aliases.length > 500
        || !value.drug.aliases.every(a => typeof a === "string" && a.length <= 240) || !Array.isArray(value.items)
        || value.items.length > 30 || !value.items.every(i => validPharmaItem(i)) || !(value.next_cursor === null || typeof value.next_cursor === "string" && value.next_cursor.length <= 300)) throw new Error("The timeline returned an invalid response.");
      if (!controller.signal.aborted) setData(previous => ({ ...value, items: cursor && previous ? [...previous.items, ...value.items.filter(i => !previous.items.some(p => p.id === i.id))] : value.items }));
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "The timeline could not be loaded."); }
    finally { if (request.current === controller) { request.current = null; setBusy(false); } }
  }, [id]);
  useEffect(() => { const timer = setTimeout(() => void load(), 0); return () => { clearTimeout(timer); request.current?.abort(); request.current = null; }; }, [load]);
  const visible = data?.items.filter(i => !material || i.impact?.rating === "Material") ?? [];
  return <section className="pi-detail-page pi-timeline-page">
    <header className="pi-detail-nav"><Link className="pi-button" href="/analyst-workspace?tool=pharma"><ArrowLeft size={15} />Pharma intelligence</Link></header>
    {data && <div className="pi-detail-content"><header className="pi-detail-overview"><h1>{data.drug.name}</h1><p className="pi-timeline-aliases">{data.drug.aliases.join(" · ")}</p><a className="pi-detail-source-link" href={data.drug.evidence_url} target="_blank" rel="noopener noreferrer">Verified identity<ArrowUpRight size={14} /></a></header>
      <div className="pi-list-heading"><h2>Drug timeline</h2><button className="pi-button pi-material-filter" aria-pressed={material} onClick={() => setMaterial(!material)}>Material only</button></div>
      <p className="pi-widget-note">Posted milestones and observed record changes · Dates in UTC</p>
      <ol className="pi-timeline">{visible.map(item => <li key={item.id}><time dateTime={item.date}>{new Date(item.date+"T00:00:00Z").toLocaleDateString(undefined, { dateStyle: "medium", timeZone: "UTC" })}</time><div><div className="pi-impact-line"><span className={`pi-impact pi-impact-${item.impact?.rating.toLowerCase()}`}>{item.impact?.rating}</span><span>{item.event?.label}</span></div><h3><Link href={pharmaRecordPath(item, { topic: "all", days: 90 })}>{item.title}<ArrowUpRight size={14} /></Link></h3><p>{item.impact?.rationale}</p><span className="pi-widget-note">{PHARMA_SOURCE_LABELS[item.source]} · {item.date_label}</span></div></li>)}</ol>
      {!visible.length && !busy && <p className="pi-widget-note">No matching events in the loaded timeline.</p>}
      {data.next_cursor && <button className="pi-button" disabled={busy} onClick={() => void load(data.next_cursor)}>Load earlier records</button>}
    </div>}
    {busy && <div className="pi-detail-state" role="status"><LoaderCircle className="pi-spinning" size={22} />Loading timeline…</div>}
    {error && <div className="pi-detail-analysis-error" role="alert"><p>{error}</p><button className="pi-button" onClick={() => void load(data?.next_cursor)}>Retry</button></div>}
  </section>;
}
