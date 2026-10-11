"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, FilePlus2, RefreshCw, Search } from "lucide-react";
import { safeURL } from "@/lib/forecasting";

type Topic = "all" | "oncology" | "rare-disease" | "immunology" | "cns" | "cardiometabolic";
type SourceId = "fda" | "trials" | "news";
export type PharmaUpdate = {
  id: string;
  source: SourceId;
  category: string;
  title: string;
  summary: string;
  date: string;
  date_label: string;
  organization: string;
  url: string;
  tags: string[];
};
type Source = {
  id: SourceId;
  name: string;
  url: string;
  cadence: string;
  scope: string;
  status:
    | "available"
    | "empty"
    | "stale"
    | "unavailable"
    | "unconfigured"
    | "authentication_required";
  checked_at: string | null;
  source_updated_at: string | null;
  items: PharmaUpdate[];
};
type Feed = {
  topic: Topic;
  days: number;
  checked_at: string;
  next_check_at: string;
  since: string;
  until: string;
  items: PharmaUpdate[];
  sources: Source[];
};
const TOPICS: { value: Topic; label: string }[] = [
  { value: "all", label: "All therapy areas" },
  { value: "oncology", label: "Oncology" },
  { value: "rare-disease", label: "Rare disease" },
  { value: "immunology", label: "Immunology" },
  { value: "cns", label: "Central nervous system" },
  { value: "cardiometabolic", label: "Cardiovascular" },
];
const STATUS = {
  available: "Connected",
  empty: "No updates in this window",
  stale: "Previous results · refresh failed",
  unavailable: "Temporarily unavailable",
  unconfigured: "News key needed",
  authentication_required: "Provider access denied",
};
function displayDate(value: string, time = false) {
  const date = new Date(value.length === 10 ? `${value}T12:00:00Z` : value);
  if (!Number.isFinite(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(time ? { hour: "2-digit", minute: "2-digit" } : { timeZone: "UTC" }),
  }).format(date);
}

export default function PharmaUpdates({
  onUseAsEvidence,
}: {
  onUseAsEvidence: (item: PharmaUpdate) => void;
}) {
  const [topic, setTopic] = useState<Topic>("all");
  const [days, setDays] = useState(7);
  const [source, setSource] = useState<SourceId | "all">("all");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(12);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const nextCheck = useRef(0);
  const requestInProgress = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    requestInProgress.current = true;
    async function load() {
      try {
        const response = await fetch(`/api/v1/pharma/updates?topic=${topic}&days=${days}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("The pharma feed could not be loaded. Please try again.");
        const data: Feed = await response.json();
        if (
          !Array.isArray(data.items) ||
          !Array.isArray(data.sources) ||
          data.topic !== topic ||
          data.days !== days
        ) {
          throw new Error("The pharma feed returned an unexpected response. Please try again.");
        }
        if (controller.signal.aborted) return;
        setFeed(data);
        nextCheck.current = new Date(data.next_check_at).getTime() || Date.now() + 3600000;
      } catch (failure) {
        if (controller.signal.aborted) return;
        setError(failure instanceof Error ? failure.message : "The pharma feed is unavailable.");
        nextCheck.current = Date.now() + 60000;
      } finally {
        if (!controller.signal.aborted) {
          requestInProgress.current = false;
          setLoading(false);
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [topic, days, refresh]);

  useEffect(() => {
    const check = () => {
      if (
        document.visibilityState === "visible" &&
        !requestInProgress.current &&
        Date.now() >= nextCheck.current
      ) {
        setRefresh((value) => value + 1);
      }
    };
    const interval = window.setInterval(check, 60000);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
    };
  }, []);

  useEffect(() => setLimit(12), [topic, days, source, query]);
  const currentFeed = feed?.topic === topic && feed.days === days ? feed : null;
  const items = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (currentFeed?.items || []).filter(
      (item) =>
        (source === "all" || item.source === source) &&
        (!needle ||
          [item.title, item.summary, item.organization, ...item.tags]
            .join(" ")
            .toLowerCase()
            .includes(needle)),
    );
  }, [currentFeed, source, query]);
  const accessible = currentFeed?.sources.some(
    (s) =>
      (source === "all" || s.id === source) && ["available", "empty", "stale"].includes(s.status),
  );

  return (
    <div className="aw-pharma">
      <div className="aw-section-heading">
        <div>
          <div className="aw-pharma-title">
            <h3>Daily pharma updates</h3>
            <span className="aw-pharma-label">Public sources</span>
          </div>
          <p>Monitor regulatory actions, trial records, and industry reporting.</p>
        </div>
        <button
          className="aw-button"
          disabled={loading}
          onClick={() => setRefresh((value) => value + 1)}
        >
          <RefreshCw size={14} className={loading ? "aw-pharma-refreshing" : ""} />
          {loading ? "Checking sources…" : "Check for updates"}
        </button>
      </div>
      <div className="aw-pharma-filters">
        <label className="aw-field sp-spaces-form-field">
          <span>Therapy area</span>
          <select value={topic} onChange={(event) => setTopic(event.target.value as Topic)}>
            {TOPICS.map((t) => (
              <option value={t.value} key={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="aw-field sp-spaces-form-field">
          <span>Date window</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {[7, 30, 90].map((value) => (
              <option value={value} key={value}>
                Last {value} days
              </option>
            ))}
          </select>
        </label>
        <label className="aw-field sp-spaces-form-field">
          <span>Update type</span>
          <select
            value={source}
            onChange={(event) => setSource(event.target.value as SourceId | "all")}
          >
            <option value="all">All updates</option>
            <option value="fda">Regulatory</option>
            <option value="trials">Clinical trials</option>
            <option value="news">Industry news</option>
          </select>
        </label>
        <label className="aw-field sp-spaces-form-field">
          <span>Search these results</span>
          <div className="aw-pharma-search">
            <Search size={15} />
            <input
              type="search"
              value={query}
              maxLength={160}
              placeholder="Drug, company, or study ID"
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </label>
      </div>
      <p className="aw-method-note">
        Therapy filters apply to trials and news. FDA records cover all therapy areas in the US.
        Search matches the loaded results.
      </p>
      {error && (
        <div className="aw-pharma-error" role="alert">
          {error}
          {currentFeed && " Previous results remain visible; their check times are shown below."}
        </div>
      )}
      <div className="aw-pharma-freshness" role="status" aria-live="polite">
        {currentFeed ? (
          <>
            <span>
              {items.length} updates{query || source !== "all" ? " matching filters" : " loaded"} ·{" "}
              {displayDate(currentFeed.since)} – {displayDate(currentFeed.until)}
            </span>
            <span>Feed checked {displayDate(currentFeed.checked_at, true)}</span>
          </>
        ) : (
          <span>{loading ? "Loading public pharma sources…" : "No feed loaded"}</span>
        )}
      </div>
      {currentFeed && (
        <div className="aw-pharma-sources" aria-label="Source availability">
          {currentFeed.sources.map((provider) => (
            <details key={provider.id} className="aw-pharma-source">
              <summary>
                <strong>{provider.name}</strong>
                <span className={`aw-pharma-status ${provider.status}`}>
                  {STATUS[provider.status]}
                  {provider.status === "available" && ` · ${provider.items.length} items`}
                </span>
              </summary>
              <div>
                <p>
                  {provider.scope}. {provider.cadence}.
                </p>
                <p>
                  {provider.items.length} recent items loaded
                  {provider.checked_at
                    ? ` · Last successful check ${displayDate(provider.checked_at, true)}`
                    : ""}
                  .
                </p>
                {provider.source_updated_at && (
                  <p>Source dataset updated {displayDate(provider.source_updated_at)}.</p>
                )}
                {provider.status === "authentication_required" && (
                  <p>
                    The provider rejected the configured credentials. Update this source’s access
                    credentials to enable its feed.
                  </p>
                )}
                {provider.status === "unconfigured" && (
                  <p>Industry reporting needs a configured news provider key.</p>
                )}
                {safeURL(provider.url) && (
                  <a href={safeURL(provider.url)} target="_blank" rel="noopener noreferrer">
                    About this source <ArrowUpRight size={12} />
                  </a>
                )}
              </div>
            </details>
          ))}
        </div>
      )}
      <div className="aw-pharma-list" aria-busy={loading}>
        {items.slice(0, limit).map((item) => (
          <article key={item.id} className="aw-pharma-item">
            <div className="aw-pharma-item-meta">
              <span>{item.category}</span>
              <span>
                {item.date_label} <time dateTime={item.date}>{displayDate(item.date)}</time>
              </span>
              {currentFeed?.sources.find((s) => s.id === item.source)?.status === "stale" && (
                <span className="aw-pharma-stale">Cached result</span>
              )}
            </div>
            <h4>{item.title}</h4>
            <p>{item.summary}</p>
            <div className="aw-pharma-tags">
              {item.tags.map((tag, index) => (
                <span key={`${tag}-${index}`}>{tag}</span>
              ))}
            </div>
            <div className="aw-pharma-item-actions">
              <span>{currentFeed?.sources.find((s) => s.id === item.source)?.name}</span>
              <div>
                {safeURL(item.url) && (
                  <a
                    className="aw-button"
                    href={safeURL(item.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Read source <ArrowUpRight size={13} />
                  </a>
                )}
                <button className="aw-button" onClick={() => onUseAsEvidence(item)}>
                  <FilePlus2 size={14} />
                  Use as evidence
                </button>
              </div>
            </div>
          </article>
        ))}
        {!items.length && !loading && (
          <div className="aw-pharma-empty">
            <h4>
              {!currentFeed || !accessible
                ? "Sources are currently unavailable"
                : "No updates match this view"}
            </h4>
            <p>
              {!currentFeed || !accessible
                ? "Check source availability above or try again shortly."
                : "Try a longer date window, another update type, or a different search."}
            </p>
          </div>
        )}
      </div>
      {items.length > limit && (
        <button
          className="aw-button aw-pharma-more"
          onClick={() => setLimit((value) => value + 12)}
        >
          Show more updates ({items.length - limit} remaining)
        </button>
      )}
      <p className="aw-method-note aw-pharma-footnote">
        Checks run on opening this tab and hourly while it is active. Sources are cached for up to
        one hour; publication schedules vary. Up to 20 recent items per source; this is a research
        feed, not an exhaustive event history. A trial record update does not establish a new
        result. Review a source before adding it as evidence or changing a forecast assumption.
      </p>
    </div>
  );
}
