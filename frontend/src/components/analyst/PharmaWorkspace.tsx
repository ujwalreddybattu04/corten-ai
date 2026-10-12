"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownToLine, ArrowUpRight, ChevronDown, ChevronLeft, ChevronRight, Clock3, Database, FileSearch, FlaskConical, RefreshCw, Search, ShieldCheck, X } from "lucide-react";
import { filterPharmaItems, PHARMA_TOPICS, pharmaCsv, PharmaFeed, PharmaItem, PharmaSource, PharmaTopic, requestPharmaFeed, retainPharmaFeed } from "@/lib/pharmaFeed";
import { saveDownload } from "@/lib/interpolationDisplay";

const SOURCE_LABELS = { fda: "FDA approvals", trials: "Clinical trials", news: "Industry news" };
const SOURCE_STATUS = { available: "Available", empty: "No recent records", stale: "Previous results · refresh failed", unavailable: "Temporarily unavailable", unconfigured: "News source not connected", authentication_required: "Provider access denied" };
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
  const filterSource = (value: string) => { setSource(value); setPage(0); setSelected(null); setNotice(""); };
  const exportCsv = () => {
    if (!feed || !filtered.length) return;
    saveDownload(new Blob([pharmaCsv(filtered, feed)], { type: "text/csv;charset=utf-8" }), `pharma-updates-${topic}-${feed.until}.csv`);
    setNotice(`${filtered.length} displayed records exported with source dates and freshness.`);
  };
  return <div className="aw-tool pi-tool">
    <div className="aw-tool-heading pi-heading">
      <div><span className="aw-eyebrow">Chryselys analyst tools</span>
        <h2>Pharma intelligence</h2>
        <p>Follow regulatory actions and drug study updates. Review the original evidence before bringing a change into your forecast.</p>
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
    <p className="pi-coverage">Therapy filters apply to trials and industry news. FDA approvals cover all therapy areas. Dates use UTC.</p>
    <div className="pi-feedback" role="status" aria-live="polite">
      {busy && <span><Clock3 size={14} aria-hidden="true" />{waiting ? "Connecting to data services. This may take a moment…" : "Checking source records…"}</span>}
      {error && <div className="pi-error" role="alert"><span>{feed?.items.length ? "Keeping the last loaded records. " : ""}{error}</span><button className="pi-button" disabled={busy} onClick={() => void load()}>Retry</button></div>}
      {notice && <span>{notice}</span>}
    </div>
    {feed && <>
      <div className="pi-summary" aria-label="Records loaded by source">
        {(["fda", "trials", "news"] as const).map(id => {
          const provider = feed.sources.find(s => s.id === id)!;
          const Icon = id === "fda" ? ShieldCheck : id === "trials" ? FlaskConical : FileSearch;
          return <button key={id} className={source === id ? "selected" : ""} aria-pressed={source === id} onClick={() => filterSource(source === id ? "all" : id)}>
            <span className="pi-summary-label"><Icon size={16} aria-hidden="true" />{SOURCE_LABELS[id]}</span>
            <strong>{["unavailable", "unconfigured", "authentication_required"].includes(provider.status) ? "—" : provider.items.length}</strong>
            <span>{provider.status === "available" ? "Recent records loaded" : SOURCE_STATUS[provider.status]}</span>
          </button>;
        })}
      </div>
      <div className="pi-content">
        <section className="pi-records" aria-labelledby="pi-records-title" aria-busy={busy}>
          <div className="pi-list-heading"><div><h3 id="pi-records-title">Recent updates</h3><p>{eventDate(feed.since)} – {eventDate(feed.until)}</p></div>
            <label className="pi-source-filter"><span className="sr-only">Record type</span><select aria-label="Record type" value={source} onChange={event => filterSource(event.target.value)}>
              <option value="all">All records</option>{Object.entries(SOURCE_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select></label>
          </div>
          <p className="pi-list-note">Newest first · {filtered.length} matching records · Up to 20 recent records per source, not market totals</p>
          {!visible.length ? <div className="pi-empty"><FileSearch size={28} strokeWidth={1.5} aria-hidden="true" /><h4>{feed.items.length ? "No matching records" : "No records in this window"}</h4>
            <p>{feed.items.length ? "Try another record type or search term." : "Choose a longer window or review source availability."}</p>
            {(query || source !== "all") && <button className="pi-button" onClick={() => { setQuery(""); filterSource("all"); }}>Clear filters</button>}
          </div> : <ol className="pi-record-list">
            {visible.map(item => <li key={item.id}>
              <div className="pi-record-meta"><span>{item.category}</span><time dateTime={item.date}>{eventDate(item.date)}</time></div>
              <h4><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}<ArrowUpRight size={14} aria-hidden="true" /><span className="sr-only"> (opens original source in a new tab)</span></a></h4>
              <p className="pi-record-summary">{item.summary || "Open the original source for the full record."}</p>
              <div className="pi-record-footer"><span>{item.date_label} · {feed.sources.find(s => s.id === item.source)?.name}</span>
                <button aria-expanded={selected === item.id} aria-controls={`pi-details-${item.id.replaceAll(":", "-")}`} onClick={() => setSelected(selected === item.id ? null : item.id)}>
                  {selected === item.id ? "Hide details" : "Record details"}<ChevronDown size={14} aria-hidden="true" />
                </button>
              </div>
              {detail?.id === item.id && <RecordDetails item={item} source={feed.sources.find(s => s.id === item.source)!} />}
            </li>)}
          </ol>}
          {filtered.length > 0 && <div className="pi-pagination"><span>{safePage * 10 + 1}–{Math.min((safePage + 1) * 10, filtered.length)} of {filtered.length}</span><div>
            <button className="pi-button" aria-label="Previous records" disabled={safePage === 0} onClick={() => { setPage(safePage - 1); setSelected(null); }}><ChevronLeft size={15} /></button>
            <button className="pi-button" aria-label="Next records" disabled={safePage === maxPage} onClick={() => { setPage(safePage + 1); setSelected(null); }}><ChevronRight size={15} /></button>
          </div></div>}
        </section>
        <aside className="pi-source-panel" aria-labelledby="pi-sources-title">
          <h3 id="pi-sources-title"><Database size={16} aria-hidden="true" />Sources & freshness</h3>
          <p>Successful source checks are shared for up to one hour. Check updates reads the latest available snapshot.</p>
          {feed.sources.map(provider => <div className="pi-source" key={provider.id}>
            <a href={provider.url} target="_blank" rel="noopener noreferrer">{provider.name}<ArrowUpRight size={13} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span></a>
            <span className={`pi-source-status ${provider.status === "stale" || provider.status === "unavailable" || provider.status === "authentication_required" ? "pi-status-attention" : ""}`}>{SOURCE_STATUS[provider.status]}</span>
            <p>{provider.scope}</p><p>{provider.cadence}</p>
            <dl><div><dt>Successful check</dt><dd>{checkedDate(provider.checked_at)}</dd></div>
              {provider.source_updated_at && <div><dt>Dataset date</dt><dd>{eventDate(provider.source_updated_at)}</dd></div>}
            </dl>
            {provider.limited && <p className="pi-limit">Showing a recent sample. More records exist at the source.</p>}
          </div>)}
          <div className="pi-reading-note"><strong>Read the date correctly</strong><p>A trial record update does not by itself mean new results, a new trial or a drug approval. Original and supplemental FDA actions are labeled separately.</p></div>
        </aside>
      </div>
    </>}
    {!feed && <div className="pi-initial" aria-busy={busy}><FlaskConical size={30} strokeWidth={1.5} aria-hidden="true" /><h3>{busy ? "Loading pharma updates" : "Pharma updates are unavailable"}</h3>
      <p>{busy ? "Gathering dated records from FDA and ClinicalTrials.gov." : "Retry the connection to load source records. No sample data is substituted."}</p>
    </div>}
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
