"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { ArrowDownToLine, ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, Clock3, Database, FileSearch, FlaskConical, RefreshCw, Search, ShieldCheck, X, LayoutGrid, List, ArrowRight } from "lucide-react";
import { filterPharmaItems, PHARMA_TOPICS, pharmaCsv, pharmaOverview, pharmaThumbnail, PharmaFeed, PharmaItem, PharmaSource, PharmaTopic, requestPharmaFeed, retainPharmaFeed } from "@/lib/pharmaFeed";
import { saveDownload } from "@/lib/interpolationDisplay";

const SOURCE_LABELS = { fda: "FDA approvals", trials: "Clinical trials", news: "Industry news" };
const SOURCE_STATUS = { available: "Available", empty: "No recent records", stale: "Previous results · refresh failed", unavailable: "Temporarily unavailable", unconfigured: "News source not connected", authentication_required: "Source access unavailable" };
function eventDate(value: string) {
  return new Date(value + "T00:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
function checkedDate(value: string | null) {
  return value ? new Date(value).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "No successful check";
}

export default function PharmaWorkspace({ active }: { active: boolean }) {
  const [topic, setTopic] = useState<PharmaTopic>("all");
  const [days, setDays] = useState<7 | 30 | 90>(7);
  const [source, setSource] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<{ key: string; feed: PharmaFeed } | null>(null);
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [view, setView] = useState<"cards" | "list">("cards");
  const sequence = useRef(0);
  const request = useRef<AbortController | null>(null);
  const lastAttempt = useRef(0);
  const snapshotRef = useRef(snapshot);
  const key = `${topic}:${days}`;
  const feed = snapshot?.key === key ? snapshot.feed : null;
  const cancelRequest = useCallback(() => {
    sequence.current++;
    request.current?.abort(); request.current = null;
    setBusy(false); setWaiting(false);
  }, []);
  const load = useCallback(async () => {
    if (!active || request.current) return;
    const id = ++sequence.current;
    const controller = new AbortController();
    request.current = controller;
    lastAttempt.current = Date.now();
    setBusy(true); setWaiting(false); setError(""); setNotice("");
    try {
      const next = await requestPharmaFeed(topic, days, controller.signal, () => {
        if (sequence.current === id) setWaiting(true);
      });
      if (sequence.current === id) {
        const value = { key: `${topic}:${days}`, feed: next };
        snapshotRef.current = value;
        setSnapshot(value);
      }
    } catch (failure) {
      if (!controller.signal.aborted && sequence.current === id) {
        const saved = snapshotRef.current;
        if (saved?.key === `${topic}:${days}`) {
          const retained = retainPharmaFeed(saved.feed);
          const value = retained ? { key: saved.key, feed: retained } : null;
          snapshotRef.current = value; setSnapshot(value);
        }
        setError(failure instanceof Error ? failure.message : "Pharma updates are temporarily unavailable. Please retry shortly.");
      }
    } finally {
      if (sequence.current === id) { request.current = null; setBusy(false); setWaiting(false); }
    }
  }, [active, topic, days]);
  useEffect(() => {
    if (!active) return;
    const check = () => {
      if (document.visibilityState !== "visible" || Date.now() - lastAttempt.current < 60_000) return;
      const saved = snapshotRef.current;
      if (!saved || saved.key !== key || Date.parse(saved.feed.next_check_at) <= Date.now()) void load();
    };
    // An explicit filter change loads its own records; data from another therapy
    // is never presented under the new filter while a request is in flight.
    const saved = snapshotRef.current;
    if (!saved || saved.key !== key || Date.parse(saved.feed.next_check_at) <= Date.now()) void load();
    const timer = window.setInterval(check, 60_000 + Math.floor(Math.random() * 10_000));
    document.addEventListener("visibilitychange", check);
    window.addEventListener("online", check);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("online", check);
      cancelRequest();
    };
  }, [active, key, load, cancelRequest]);

  const filtered = useMemo(() => filterPharmaItems(feed?.items ?? [], source, query), [feed, source, query]);
  const maxPage = Math.max(0, Math.ceil(filtered.length / 10) - 1);
  const safePage = Math.min(page, maxPage);
  const visible = filtered.slice(safePage * 10, safePage * 10 + 10);
  const detail = filtered.find(item => item.id === selected);
  const activeProvider = feed?.sources.find(s => s.id === source);
  const sourceUnavailable = activeProvider && ["unavailable", "unconfigured", "authentication_required"].includes(activeProvider.status);
  const overview = useMemo(() => feed ? pharmaOverview(feed) : null, [feed]);
  const highlights = feed ? [feed.items.find(i => i.source === "fda"), feed.items.find(i => i.source === "trials")].filter((item): item is PharmaItem => !!item) : [];
  const filterSource = (value: string) => { setSource(value); setPage(0); setSelected(null); setNotice(""); };
  const reviewRecord = (item: PharmaItem) => {
    setQuery(""); setSource(item.source); setPage(0); setSelected(item.id);
    window.requestAnimationFrame(() => document.getElementById("pi-records-title")?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" }));
  };
  const exportCsv = () => {
    if (!feed || !filtered.length) return;
    saveDownload(new Blob([pharmaCsv(filtered, feed)], { type: "text/csv;charset=utf-8" }), `pharma-updates-${topic}-${feed.until}.csv`);
    setNotice(`${filtered.length} displayed records exported with source dates and freshness.`);
  };
  return <div className="aw-tool pi-tool">
    <div className="aw-tool-heading pi-heading">
      <div>
        <h2>Pharma intelligence</h2>
        {feed && <div className="pi-header-status"><span className={feed.status === "stale" ? "pi-status-attention" : ""}>{feed.status === "stale" ? "Previous snapshot" : "Updated"} · {checkedDate(feed.checked_at)}</span><span>{feed.sources.filter(s => ["available", "empty"].includes(s.status)).length} / 3 sources available</span></div>}
      </div>
      <div className="pi-actions">
        <button className="pi-button" onClick={() => void load()} disabled={busy}>
          <RefreshCw size={15} className={busy ? "pi-spinning" : ""} aria-hidden="true" />{busy ? "Checking…" : "Check updates"}
        </button>
        <button className="pi-button" onClick={exportCsv} disabled={!filtered.length || busy}><ArrowDownToLine size={15} aria-hidden="true" />Export CSV</button>
      </div>
    </div>
    <div className="pi-filter-panel">
      <label>Therapy area<select value={topic} onChange={event => { setTopic(event.target.value as PharmaTopic); setPage(0); setSelected(null); setError(""); }}>
        {PHARMA_TOPICS.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select></label>
      <label>Date window<select value={days} onChange={event => { setDays(Number(event.target.value) as 7 | 30 | 90); setPage(0); setSelected(null); setError(""); }}>
        {[7, 30, 90].map(day => <option key={day} value={day}>Last {day} days</option>)}
      </select></label>
      <label className="pi-search-label">Search loaded records<span className="pi-search"><Search size={15} aria-hidden="true" /><input value={query} maxLength={160} placeholder="Drug, company, condition or study ID" onChange={event => { setQuery(event.target.value); setPage(0); setSelected(null); }} />
        {query && <button aria-label="Clear record search" onClick={() => { setQuery(""); setPage(0); }}><X size={14} /></button>}
      </span></label>
    </div>
    <p className="pi-coverage">FDA: all therapy areas · Dates in UTC</p>
    <div className="pi-feedback" role="status" aria-live="polite">
      {busy && <span><Clock3 size={14} aria-hidden="true" />{waiting ? "Connecting…" : "Checking updates…"}</span>}
      {error && <div className="pi-error" role="alert"><span>{feed?.items.length ? "Keeping the last loaded records. " : ""}{error}</span><button className="pi-button" disabled={busy} onClick={() => void load()}>Retry</button></div>}
      {notice && <span>{notice}</span>}
    </div>
    {feed && <>
      <div className="pi-summary" aria-label="Records loaded by source">
        {(["fda", "trials", "news"] as const).map(id => {
          const provider = feed.sources.find(s => s.id === id)!;
          const Icon = id === "fda" ? ShieldCheck : id === "trials" ? FlaskConical : FileSearch;
          return <button key={id} className={source === id ? "selected" : ""} aria-pressed={source === id} onClick={() => filterSource(source === id ? "all" : id)}>
            <span className="pi-summary-label"><span className={`pi-widget-icon pi-tone-${id}`}><Icon size={16} aria-hidden="true" /></span>{SOURCE_LABELS[id]}<ArrowUpRight className="pi-widget-arrow" size={15} aria-hidden="true" /></span>
            <strong>{["unavailable", "unconfigured", "authentication_required"].includes(provider.status) ? "—" : provider.items.length}</strong>
            <span><span className={`pi-status-dot pi-dot-${provider.status}`} />{provider.status === "available" ? "Loaded" : SOURCE_STATUS[provider.status]}</span>
          </button>;
        })}
      </div>
      {highlights.length > 0 && !query && source === "all" && <section className="pi-highlights" aria-labelledby="pi-highlights-title"><div className="pi-section-heading"><h3 id="pi-highlights-title">Latest by source</h3></div>
        <div className="pi-highlight-grid">{highlights.map(item => <article className="pi-highlight-card" key={item.id}><RecordThumbnail item={item} featured /><div className="pi-highlight-body"><span className={`pi-record-kind pi-tone-${item.source}`}>{item.source === "fda" ? "Latest FDA action" : "Latest study update"}</span><h4 title={item.title}>{item.title}</h4><p>{item.organization || "Organization not listed"}</p><div><time dateTime={item.date}>{eventDate(item.date)}</time><button onClick={() => reviewRecord(item)}>Review record<ArrowRight size={14} aria-hidden="true" /></button></div></div></article>)}</div>
      </section>}
      {overview && feed.items.length > 0 && <div className="pi-insight-grid">
        <section className="pi-activity-widget" aria-labelledby="pi-activity-title">
          <div className="pi-widget-heading"><h3 id="pi-activity-title">Loaded record dates</h3><span className="pi-widget-total">{feed.items.length}<small>records</small></span></div>
          <svg className="pi-activity-chart" viewBox="0 0 560 106" role="img" aria-label={`Dates of ${feed.items.length} loaded records; a capped source sample, not total market activity`}>
            {[20, 52, 84].map(y => <line key={y} x1="0" x2="560" y1={y} y2={y} stroke="currentColor" opacity="0.1" />)}
            {overview.bins.map((bin, index) => {
              const peak = Math.max(1, ...overview.bins.map(b => b.fda + b.trials + b.news));
              let stacked = 0;
              return <g key={bin.date}><title>{eventDate(bin.date)} onwards: {bin.fda} FDA actions, {bin.trials} study updates, {bin.news} news articles</title>
                {(["fda", "trials", "news"] as const).map(id => { const height = bin[id] / peak * 72; const y = 84 - stacked - height; stacked += height;
                  return <rect className={`pi-chart-${id}`} key={id} x={index * 560 / overview.bins.length + 8} y={y} width={560 / overview.bins.length - 16} height={height} rx="3" />; })}
              </g>;
            })}
          </svg>
          <div className="pi-chart-axis"><span>{eventDate(feed.since)}</span><span>{eventDate(feed.until)}</span></div>
          <div className="pi-chart-legend"><span><i className="pi-tone-fda" />FDA actions</span><span><i className="pi-tone-trials" />Study updates</span><span><i className="pi-tone-news" />News</span></div>
          <p className="pi-widget-note">Sample · Up to 20 records per source</p>
        </section>
        <section className="pi-phase-widget" aria-labelledby="pi-phase-title"><div className="pi-widget-heading"><h3 id="pi-phase-title">Clinical study phases</h3><FlaskConical size={19} aria-hidden="true" /></div>
          {overview.trials ? <div className="pi-phase-bars" tabIndex={0} role="region" aria-label="Loaded study phase breakdown">{overview.phases.map(phase => <div key={phase.label}><div><span>{phase.label}</span><strong>{phase.count}</strong></div><div className="pi-phase-track"><span style={{ width: `${phase.count / overview.trials * 100}%` }} /></div></div>)}</div> : <p className="pi-widget-note">No study records loaded in this window. Review ClinicalTrials.gov availability below.</p>}
          <p className="pi-widget-note">{overview.trials} loaded studies</p>
        </section>
      </div>}
      <div className="pi-content">
        <section className="pi-records" aria-labelledby="pi-records-title" aria-busy={busy}>
          <div className="pi-list-heading"><div><h3 id="pi-records-title">Research feed</h3><p>{eventDate(feed.since)} – {eventDate(feed.until)}</p></div>
            <div className="pi-feed-controls"><div className="pi-view-toggle" role="group" aria-label="Record layout"><button aria-label="Card view" aria-pressed={view === "cards"} onClick={() => setView("cards")}><LayoutGrid size={15} /></button><button aria-label="List view" aria-pressed={view === "list"} onClick={() => setView("list")}><List size={16} /></button></div>
            <label className="pi-source-filter"><span className="sr-only">Record type</span><select aria-label="Record type" value={source} onChange={event => filterSource(event.target.value)}>
              <option value="all">All records</option>{Object.entries(SOURCE_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select></label>
            </div>
          </div>
          <p className="pi-list-note">{filtered.length} records · Newest first</p>
          {!visible.length ? <div className="pi-empty"><FileSearch size={28} strokeWidth={1.5} aria-hidden="true" /><h4>{sourceUnavailable ? `${SOURCE_LABELS[activeProvider.id]} unavailable` : feed.items.length ? "No matching records" : "No records in this window"}</h4>
            <p>{sourceUnavailable ? "Choose another record type or review the source status panel. Other loaded records remain available." : feed.items.length ? "Try another record type or search term." : "Choose a longer window or review source availability."}</p>
            {(query || source !== "all") && <button className="pi-button" onClick={() => { setQuery(""); filterSource("all"); }}>Clear filters</button>}
          </div> : <ol className={`pi-record-list pi-layout-${view}`}>
            {visible.map(item => <li key={item.id}>
              <RecordThumbnail item={item} />
              <div className="pi-record-body">
              <div className="pi-record-meta"><span>{item.category}</span><time dateTime={item.date}>{eventDate(item.date)}</time></div>
              <h4><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<ArrowUpRight size={14} aria-hidden="true" /><span className="sr-only"> (opens original source in a new tab)</span></a></h4>
              <p className="pi-record-summary">{item.summary || "Open the original source for the full record."}</p>
              <div className="pi-record-footer"><span>{item.date_label} · {feed.sources.find(s => s.id === item.source)?.name}</span>
                <button aria-expanded={selected === item.id} aria-controls={`pi-details-${item.id.replaceAll(":", "-")}`} onClick={() => setSelected(selected === item.id ? null : item.id)}>
                  {selected === item.id ? "Hide details" : "Record details"}<ChevronDown size={14} aria-hidden="true" />
                </button>
              </div>
              {detail?.id === item.id && <RecordDetails item={item} source={feed.sources.find(s => s.id === item.source)!} />}
              </div>
            </li>)}
          </ol>}
          {filtered.length > 0 && <div className="pi-pagination"><span>{safePage * 10 + 1}–{Math.min((safePage + 1) * 10, filtered.length)} of {filtered.length}</span><div>
            <button className="pi-button" aria-label="Previous records" disabled={safePage === 0} onClick={() => { setPage(safePage - 1); setSelected(null); }}><ChevronLeft size={15} /></button>
            <button className="pi-button" aria-label="Next records" disabled={safePage === maxPage} onClick={() => { setPage(safePage + 1); setSelected(null); }}><ChevronRight size={15} /></button>
          </div></div>}
        </section>
        <aside className="pi-source-panel" aria-labelledby="pi-sources-title">
          <h3 id="pi-sources-title"><Database size={16} aria-hidden="true" />Sources & freshness</h3>
          {feed.sources.map(provider => <div className="pi-source" key={provider.id}>
            <a href={provider.url} target="_blank" rel="noopener noreferrer">{provider.name}<ArrowUpRight size={13} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span></a>
            <span className={`pi-source-status ${provider.status === "stale" || provider.status === "unavailable" || provider.status === "authentication_required" ? "pi-status-attention" : ""}`}>{SOURCE_STATUS[provider.status]}</span>
            <p>{provider.scope}</p><p>{provider.cadence}</p>
            <dl><div><dt>Successful check</dt><dd>{checkedDate(provider.checked_at)}</dd></div>
              {provider.source_updated_at && <div><dt>Dataset date</dt><dd>{eventDate(provider.source_updated_at)}</dd></div>}
            </dl>
            {provider.limited && <p className="pi-limit">Recent sample</p>}
          </div>)}
          <details className="pi-reading-note"><summary>Data notes</summary><p>Trials and news use the therapy filter; FDA actions cover all therapies. Updates indicate record changes, not new results or approvals. Charts show a capped sample, not market totals. Source checks are cached for up to one hour.</p></details>
        </aside>
      </div>
    </>}
    {!feed && <div className="pi-initial" aria-busy={busy}><FlaskConical size={30} strokeWidth={1.5} aria-hidden="true" /><h3>{busy ? "Loading pharma updates" : "Pharma updates are unavailable"}</h3>
      {!busy && <p>Check updates to retry.</p>}
    </div>}
  </div>;
}

function RecordThumbnail({ item, featured = false }: { item: PharmaItem; featured?: boolean }) {
  const [failed, setFailed] = useState("");
  const image = item.source === "news" ? pharmaThumbnail(item.thumbnail) : null;
  const identifier = item.details?.study_id ?? item.details?.application;
  return <div className={`pi-thumbnail pi-thumbnail-${item.source}${featured ? " pi-thumbnail-featured" : ""}`}>
    {image && failed !== image ? <><Image src={image} alt="" width={560} height={280} unoptimized loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(image)} /><span className="pi-thumb-caption">Publisher image</span></> : <>
      <svg viewBox="0 0 300 140" aria-hidden="true" className="pi-thumb-art"><g fill="none" stroke="currentColor" strokeWidth="1.3">
        {item.source === "trials" ? <>{[0, 1, 2, 3, 4, 5].map(n => <g key={n}><path d={`M${158 + Math.sin(n * 1.1) * 25},${12 + n * 21} L${158 - Math.sin(n * 1.1) * 25},${12 + n * 21}`} opacity=".55" /><circle cx={158 + Math.sin(n * 1.1) * 25} cy={12 + n * 21} r="3" fill="currentColor" /></g>)}<path d="M158 12 C208 42 108 86 158 128 M158 12 C108 42 208 86 158 128" /></> : <><path d="M156 20l27 16v32l-27 16-27-16V36z M183 68l27-16 27 16v32l-27 16-27-16z M129 68l-27 16v32l27 16 27-16V84" /><path d="M156 20V4 M237 68l27-16 M102 116l-25 14" /><circle cx="156" cy="4" r="3" fill="currentColor" /><circle cx="264" cy="52" r="3" fill="currentColor" /></>}
      </g></svg><span className="pi-thumb-overline">{item.source === "fda" ? "Regulatory record" : item.source === "trials" ? "Clinical study" : "Industry reporting"}</span><span className="pi-thumb-id">{identifier ?? (item.source === "news" ? "Pharma & biotech" : "Source record")}</span><span className="pi-thumb-caption">Illustrated record preview</span>
    </>}
  </div>;
}

function RecordDetails({ item, source }: { item: PharmaItem; source: PharmaSource }) {
  const facts = item.details ? Object.entries(item.details).filter(([, v]) => typeof v === "string" ? !!v : Array.isArray(v) && v.length > 0) : [];
  const labels: Record<string, string> = { application: "Application", action: "Action", ingredients: "Active ingredients", study_id: "Study ID", status: "Study status", phases: "Trial phases", conditions: "Conditions", interventions: "Drug / biologic interventions" };
  return <div className="pi-details" id={`pi-details-${item.id.replaceAll(":", "-")}`}>
    <dl>{facts.map(([label, value]) => <div key={label}><dt>{labels[label] ?? label}</dt><dd>{Array.isArray(value) ? value.map(v => v.replace(/^PHASE/, "Phase ")).join(" · ") : value}</dd></div>)}
      <div><dt>Organization</dt><dd>{item.organization || "Not listed"}</dd></div>
      <div><dt>Source freshness</dt><dd>{SOURCE_STATUS[source.status]} · {checkedDate(source.checked_at)}</dd></div>
    </dl><a href={item.url} target="_blank" rel="noopener noreferrer">Open original record<ArrowUpRight size={14} aria-hidden="true" /></a>
  </div>;
}
