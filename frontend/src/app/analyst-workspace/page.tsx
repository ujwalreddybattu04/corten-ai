"use client";
import { accountStorage } from "@/lib/accountStorage";


import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import PharmaUpdates from "@/components/analyst/PharmaUpdates";
import {
  ArrowDownToLine,
  ArrowUpRight,
  Check,
  ChevronDown,
  FileText,
  History,
  Plus,
  Search,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import {
  createProject,
  exportCSV,
  forecastProject,
  isProject,
  parseMonthlyCSV,
  safeURL,
  SAMPLE_SERIES,
  validMonth,
  type ForecastProject,
  type ForecastRow,
  type PatientInputs,
  type ScenarioName,
} from "@/lib/forecasting";
import "@/styles/analyst-workspace.css";

const STORAGE_KEY = "corten_analyst_projects_v1";
const SELECTED_KEY = "corten_analyst_selected_v1";
const WORKSPACE_TABS = [
  "Overview",
  "Pharma updates",
  "Model inputs",
  "Scenarios",
  "Evidence & review",
  "Monthly outputs",
];
const COLORS = {
  Base: "var(--color-text-primary)",
  Upside: "var(--color-success)",
  Downside: "var(--color-warning)",
};
const compact = (value: number) =>
  new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
const number = (value: number) =>
  new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(value);
const month = (date: string) =>
  new Date(`${date}-01T12:00:00Z`).toLocaleDateString("en", {
    month: "short",
    year: "2-digit",
    timeZone: "UTC",
  });
const total = (rows: ForecastRow[]) => rows.reduce((sum, row) => sum + row.netSales, 0);
function reviewDate(value: string, includeTime = false) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function NumericField({
  label,
  value,
  onChange,
  min = 0,
  max = 1e9,
  suffix = "",
  hint = "",
  integer = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  suffix?: string;
  hint?: string;
  integer?: boolean;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => {
    const parsed = Number(draft);
    if (draft.trim() && Number.isFinite(parsed)) {
      const bounded = Math.min(max, Math.max(min, integer ? Math.round(parsed) : parsed));
      setDraft(String(bounded));
      onChange(bounded);
    } else setDraft(String(value));
  };
  return (
    <label className="aw-field sp-spaces-form-field">
      <span>{label}</span>
      <div className="aw-number-input">
        <input
          type="number"
          min={min}
          max={max}
          step={integer ? 1 : "any"}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit();
          }}
        />
        {suffix && <span>{suffix}</span>}
      </div>
      {hint && <small>{hint}</small>}
    </label>
  );
}

function ForecastChart({
  project,
  rows,
}: {
  project: ForecastProject;
  rows: Record<ScenarioName, ForecastRow[]>;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(960);
  useEffect(() => {
    if (!chartRef.current) return;
    const observer = new ResizeObserver((entries) =>
      setChartWidth(Math.max(260, Math.round(entries[0].contentRect.width))),
    );
    observer.observe(chartRef.current);
    return () => observer.disconnect();
  }, [project.mode, project.series.length]);
  const historical = project.mode === "historical" ? project.series.slice(-24) : [];
  const valueOf = (row: ForecastRow) =>
    project.mode === "patient" ? row.patients || 0 : row.volume;
  const values = [
    ...historical.map((row) => row.value),
    ...Object.values(rows).flatMap((data) => data.map(valueOf)),
  ];
  if (!values.length)
    return (
      <div className="aw-chart-empty">
        <Upload size={28} />
        <p>Import monthly volume data or switch to a patient-based model.</p>
      </div>
    );
  const width = chartWidth,
    height = width < 500 ? 240 : 280,
    left = 62,
    top = 20,
    bottom = height - 48,
    right = width - 24;
  const count = historical.length + rows.Base.length;
  const max = Math.max(1, ...values) * 1.13;
  const x = (index: number) => left + (index / Math.max(1, count - 1)) * (right - left);
  const y = (value: number) => bottom - (value / max) * (bottom - top);
  const points = (data: { index: number; value: number }[]) =>
    data.map((row) => `${x(row.index)},${y(row.value)}`).join(" ");
  const dates = [...historical.map((row) => row.date), ...rows.Base.map((row) => row.date)];
  const selected = hover !== null ? Math.min(hover, count - 1) : null;
  return (
    <div className="aw-chart-wrap" ref={chartRef}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        tabIndex={0}
        aria-label={
          project.mode === "patient"
            ? "Monthly active brand patients under three planning scenarios"
            : "Historical volume and three forecast scenarios"
        }
        onPointerMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const coordinate = ((event.clientX - box.left) / box.width) * width;
          setHover(
            Math.max(
              0,
              Math.min(count - 1, Math.round(((coordinate - left) / (right - left)) * (count - 1))),
            ),
          );
        }}
        onPointerLeave={() => setHover(null)}
        onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Escape"].includes(event.key)) return;
          event.preventDefault();
          setHover(
            event.key === "Escape"
              ? null
              : Math.max(
                  0,
                  Math.min(
                    count - 1,
                    (hover ?? historical.length) + (event.key === "ArrowRight" ? 1 : -1),
                  ),
                ),
          );
        }}
      >
        {[0, 1, 2, 3, 4].map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              x2={right}
              y1={y((max * tick) / 4)}
              y2={y((max * tick) / 4)}
              className="aw-gridline"
            />
            <text x={left - 12} y={y((max * tick) / 4) + 4} textAnchor="end">
              {compact((max * tick) / 4)}
            </text>
          </g>
        ))}
        {historical.length > 0 && (
          <>
            <rect
              x={x(historical.length - 1)}
              y={top}
              width={right - x(historical.length - 1)}
              height={bottom - top}
              fill="var(--color-text-primary)"
              opacity=".035"
            />
            <line
              x1={x(historical.length - 1)}
              x2={x(historical.length - 1)}
              y1={top}
              y2={bottom}
              stroke="var(--color-text-tertiary)"
              strokeDasharray="4 5"
            />
          </>
        )}
        {historical.length > 0 && (
          <polyline
            points={points(historical.map((row, index) => ({ index, value: row.value })))}
            fill="none"
            stroke="var(--color-text-secondary)"
            strokeWidth="2.5"
          />
        )}
        {(Object.keys(rows) as ScenarioName[]).map((name) => {
          const data = rows[name].map((row, index) => ({
            index: historical.length + index,
            value: valueOf(row),
          }));
          if (historical.length)
            data.unshift({
              index: historical.length - 1,
              value: historical[historical.length - 1].value,
            });
          return (
            <polyline
              key={name}
              points={points(data)}
              fill="none"
              stroke={COLORS[name]}
              strokeWidth={name === "Base" ? 3 : 2}
              strokeDasharray={name === "Base" ? undefined : "5 5"}
            />
          );
        })}
        {dates.map((date, index) =>
          (index % Math.max(1, Math.ceil(count / (width < 500 ? 4 : 7))) === 0 &&
            index < count - 2) ||
          index === count - 1 ? (
            <text key={date} x={x(index)} y={bottom + 25} textAnchor="middle">
              {month(date)}
            </text>
          ) : null,
        )}
        {selected !== null && (
          <line
            x1={x(selected)}
            x2={x(selected)}
            y1={top}
            y2={bottom}
            stroke="var(--color-text-secondary)"
            strokeDasharray="3 4"
            opacity=".5"
          />
        )}
      </svg>
      {selected !== null && (
        <div className="aw-chart-tooltip" aria-live="polite">
          <strong>{month(dates[selected])}</strong>
          {selected < historical.length ? (
            <span>Historical volume: {number(historical[selected].value)}</span>
          ) : (
            (Object.keys(rows) as ScenarioName[]).map((name) => (
              <span key={name}>
                <i style={{ background: COLORS[name] }} />
                {name}: {number(valueOf(rows[name][selected - historical.length]))}
              </span>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function AnalystWorkspace() {
  const [projects, setProjects] = useState<ForecastProject[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [tab, setTab] = useState("Overview");
  const [projectSearch, setProjectSearch] = useState("");
  const [contextOpen, setContextOpen] = useState(false);
  const [saveState, setSaveState] = useState<"saved" | "unavailable">("saved");
  const [restoreFailureRaw, setRestoreFailureRaw] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [evidenceTitle, setEvidenceTitle] = useState("");
  const [evidenceURL, setEvidenceURL] = useState("");
  const [evidenceRationale, setEvidenceRationale] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let initial: ForecastProject[] = [];
    let remembered = "";
    let raw: string | null = null;
    try {
      remembered = accountStorage.getItem(SELECTED_KEY) || "";
      raw = accountStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved: unknown = JSON.parse(raw);
        if (Array.isArray(saved)) initial = saved.filter(isProject).slice(0, 20);
        if (!Array.isArray(saved) || initial.length !== saved.length) {
          setRestoreFailureRaw(raw);
          setNotice(
            "Some saved projects could not be restored. Original stored data has been preserved; export review packs to keep new work.",
          );
        }
      }
    } catch {
      if (raw) {
        setRestoreFailureRaw(raw);
        setNotice(
          "Saved projects could not be read. Original stored data has been preserved; export review packs to keep new work.",
        );
      } else {
        setNotice("Browser storage is unavailable. Export a review pack to keep your work.");
      }
    }
    if (!initial.length) initial = [createProject(true)];
    setProjects(initial);
    setSelectedId(initial.some((item) => item.id === remembered) ? remembered : initial[0].id);
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (!loaded) return;
    if (restoreFailureRaw !== null) {
      setSaveState("unavailable");
      return;
    }
    try {
      accountStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
      accountStorage.setItem(SELECTED_KEY, selectedId);
      setSaveState("saved");
    } catch {
      setSaveState("unavailable");
      setNotice("This device could not save your changes. Export a review pack to keep your work.");
    }
  }, [projects, loaded, selectedId, restoreFailureRaw]);

  const project = projects.find((item) => item.id === selectedId) || projects[0];
  const result = useMemo(() => (project ? forecastProject(project) : null), [project]);
  const update = (changes: Partial<ForecastProject>) =>
    setProjects((current) =>
      current.map((item) => (item.id === project.id ? { ...item, ...changes } : item)),
    );
  const updatePatient = (key: keyof PatientInputs, value: number) =>
    update({ patient: { ...project.patient, [key]: value } });
  const chooseProject = (id: string) => {
    setSelectedId(id);
    setContextOpen(false);
    setNotice("");
    setTab("Overview");
    setEvidenceTitle("");
    setEvidenceURL("");
    setEvidenceRationale("");
  };
  const openContext = () => {
    setContextOpen(true);
    requestAnimationFrame(() => {
      document
        .querySelector(".aw-context")
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
      document.querySelector<HTMLInputElement>(".aw-scope input")?.focus({ preventScroll: true });
    });
  };
  const money = (value: number, currency = project.currency) =>
    new Intl.NumberFormat("en", {
      style: "currency",
      currency,
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);

  async function importFile(file?: File) {
    if (!file || !project) return;
    try {
      if (file.size > 2_000_000) throw new Error("Choose a CSV or review pack smaller than 2 MB.");
      const text = await file.text();
      if (file.name.toLowerCase().endsWith(".json")) {
        if (projects.length >= 20) throw new Error("This local workspace supports 20 projects.");
        const pack = JSON.parse(text);
        if (pack.schema !== "corten-forecast-review-v1" || !isProject(pack.project))
          throw new Error("This is not a valid Corten forecast review pack.");
        const restored = {
          ...pack.project,
          id: crypto.randomUUID(),
          name: `${pack.project.name} · imported`,
        };
        setProjects((current) => [...current, restored]);
        chooseProject(restored.id);
        setProjectSearch("");
        setNotice("Review pack imported as a separate project.");
      } else {
        const series = parseMonthlyCSV(text);
        update({ series, mode: "historical", sample: false, model: "auto" });
        setNotice(`${series.length} monthly observations validated and imported.`);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not import this file.");
    }
    if (fileRef.current) fileRef.current.value = "";
  }
  const newProject = () => {
    if (projects.length >= 20) {
      setNotice(
        "This local workspace supports 20 projects. Export your projects before starting another workspace.",
      );
      return;
    }
    const next = createProject(false);
    setProjects((current) => [...current, next]);
    chooseProject(next.id);
    setProjectSearch("");
    setContextOpen(true);
    setTab("Model inputs");
    setNotice("");
  };
  const saveVersion = () => {
    if (!project || !result?.rows.Base.length) return;
    const { versions, ...inputs } = project;
    const reviewNumber =
      Math.max(
        0,
        ...versions.map((version) => Number(version.name.match(/^Review (\d+)$/)?.[1] || 0)),
      ) + 1;
    update({
      versions: [
        ...versions.slice(-19),
        {
          id: crypto.randomUUID(),
          savedAt: new Date().toISOString(),
          name: `Review ${reviewNumber}`,
          inputs: structuredClone(inputs),
          rows: structuredClone(result.rows),
        },
      ],
    });
    setNotice("Review version saved with its inputs, evidence, and monthly outputs.");
  };
  const addEvidence = () => {
    if (!evidenceTitle.trim() || !evidenceRationale.trim()) {
      setNotice("Add an evidence title and explain which assumption it supports.");
      return;
    }
    if (evidenceURL && !safeURL(evidenceURL)) {
      setNotice("Use an http or https source URL, or leave it blank for internal evidence.");
      return;
    }
    update({
      evidence: [
        ...project.evidence,
        {
          id: crypto.randomUUID(),
          title: evidenceTitle.trim(),
          url: evidenceURL.trim(),
          rationale: evidenceRationale.trim(),
          addedAt: new Date().toISOString(),
        },
      ],
    });
    setEvidenceTitle("");
    setEvidenceURL("");
    setEvidenceRationale("");
    setNotice("Evidence added to the project.");
  };

  if (!project || !result) return <div className="aw-loading">Opening Analyst Workspace…</div>;
  const ready = result.rows.Base.length > 0;
  const baseTotal = total(result.rows.Base),
    upsideTotal = total(result.rows.Upside),
    downsideTotal = total(result.rows.Downside);
  const bestScore = result.scores.find((score) => score.label === result.selectedModel);
  const { versions: reviewVersions, ...currentInputs } = project;
  const latestReview = reviewVersions.at(-1);
  const snapshotCurrent =
    !!latestReview && JSON.stringify(latestReview.inputs) === JSON.stringify(currentInputs);
  const filteredProjects = projects.filter((item) =>
    `${item.name} ${item.brand} ${item.country} ${item.therapy} ${item.owner}`
      .toLowerCase()
      .includes(projectSearch.trim().toLowerCase()),
  );
  const reviewTasks = [
    {
      label: "Forecast baseline",
      detail: ready
        ? `${project.horizon} monthly periods calculated`
        : "Add data or configure a patient model",
      done: ready,
      action: () => setTab("Model inputs"),
    },
    {
      label: "Forecast ownership",
      detail:
        project.owner && project.brand
          ? `${project.owner} · ${project.brand}`
          : "Assign an analyst and identify the asset",
      done: !!project.owner.trim() && !!project.brand.trim(),
      action: openContext,
    },
    {
      label: "Assumption evidence",
      detail: project.evidence.length
        ? `${project.evidence.length} supporting source${project.evidence.length === 1 ? "" : "s"} attached`
        : "Link sources and document your rationale",
      done: project.evidence.length > 0,
      action: () => setTab("Evidence & review"),
    },
    {
      label: "Review snapshot",
      detail: snapshotCurrent
        ? "Current inputs and outputs captured"
        : latestReview
          ? "Inputs changed since the last snapshot"
          : "Capture a version to share for review",
      done: snapshotCurrent,
      action: () => setTab("Evidence & review"),
    },
  ];
  const explanation = `Summarize this text: Commercial planning scenario for ${project.brand || "an unnamed brand"}, ${project.therapy}, ${project.country}. Model: ${result.selectedModel}; horizon: ${project.horizon} months. Forecast net sales: base ${number(baseTotal)} ${project.currency}, upside ${number(upsideTotal)}, downside ${number(downsideTotal)}. Unit price ${project.price}; gross-to-net deduction ${project.g2n}%. ${project.mode === "patient" ? `Patient assumptions: existing prevalent population ${project.patient.existingPatients}, annual incidence ${project.patient.annualIncidence}, diagnosis ${project.patient.diagnosis}%, eligibility ${project.patient.eligibility}%, monthly initiation ${project.patient.initiation}%, brand capture ${project.patient.capture}%, monthly discontinuation ${project.patient.discontinuation}%.` : `Backtest: ${result.holdout} months; selected baseline WAPE ${bestScore?.wape?.toFixed(1) || "unavailable"}%.`} Explain the drivers and limitations using only these supplied numbers. Scenarios are assumptions, not prediction intervals.`;

  return (
    <div className="aw-page">
      <header className="aw-header">
        <div className="aw-header-title">
          <h1>Analyst Workspace</h1>
          <span>Commercial forecasting</span>
        </div>
        <div className="aw-header-actions">
          <span className="aw-save-status" role="status">
            {saveState === "saved" ? "Saved on this device" : "Export to keep changes"}
          </span>
          <button className="sp-spaces-create-btn aw-primary" onClick={newProject}>
            <Plus size={16} />
            New forecast
          </button>
        </div>
      </header>
      {restoreFailureRaw !== null && (
        <div className="aw-notice aw-recovery" role="alert">
          <span>
            Original stored data needs recovery and has been preserved. Export review packs to keep
            new work.
          </span>
          <button
            onClick={() =>
              download("workspace-recovery.json", restoreFailureRaw, "application/json")
            }
          >
            Download original stored data
          </button>
        </div>
      )}
      {notice && (
        <div className="aw-notice" role="status">
          <span>{notice}</span>
          <button onClick={() => setNotice("")} aria-label="Dismiss notification">
            <X size={16} />
          </button>
        </div>
      )}
      <div className="aw-layout">
        <aside className="aw-project-panel">
          <div className="aw-panel-caption">
            FORECASTS <span>{projects.length}</span>
          </div>
          <label className="aw-project-search">
            <Search size={16} aria-hidden="true" />
            <input
              aria-label="Find a forecast"
              placeholder="Find a forecast"
              value={projectSearch}
              onChange={(event) => setProjectSearch(event.target.value)}
            />
          </label>
          <div className="aw-project-list">
            {filteredProjects.map((item) => (
              <button
                key={item.id}
                className={`aw-project-item ${item.id === project.id ? "selected" : ""}`}
                aria-pressed={item.id === project.id}
                title={item.name}
                onClick={() => chooseProject(item.id)}
              >
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {item.therapy} · {item.country}
                  </small>
                </span>
              </button>
            ))}
            {!filteredProjects.length && (
              <p className="aw-search-empty">No forecasts match your search.</p>
            )}
          </div>
          <label className="aw-mobile-project-picker">
            <span>Forecast</span>
            <select value={project.id} onChange={(event) => chooseProject(event.target.value)}>
              {projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name || "Untitled forecast"}
                </option>
              ))}
            </select>
          </label>
          <details
            className="aw-context"
            open={contextOpen}
            onToggle={(event) => setContextOpen(event.currentTarget.open)}
          >
            <summary>
              Edit forecast details <ChevronDown size={16} />
            </summary>
            <div className="aw-scope">
              <label className="aw-field sp-spaces-form-field">
                <span>Project name</span>
                <input
                  value={project.name}
                  maxLength={90}
                  onChange={(event) => update({ name: event.target.value })}
                />
              </label>
              <label className="aw-field sp-spaces-form-field">
                <span>Brand / asset</span>
                <input
                  placeholder="Brand or development asset"
                  value={project.brand}
                  maxLength={80}
                  onChange={(event) => update({ brand: event.target.value })}
                />
              </label>
              <label className="aw-field sp-spaces-form-field">
                <span>Therapy area</span>
                <select
                  value={project.therapy}
                  onChange={(event) => update({ therapy: event.target.value })}
                >
                  {[
                    "Oncology",
                    "Rare disease",
                    "Immunology",
                    "CNS",
                    "Cardiometabolic",
                    "Other",
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label className="aw-field sp-spaces-form-field">
                <span>Market</span>
                <input
                  value={project.country}
                  maxLength={60}
                  onChange={(event) => update({ country: event.target.value })}
                />
              </label>
              <label className="aw-field sp-spaces-form-field">
                <span>Lifecycle</span>
                <select
                  value={project.lifecycle}
                  onChange={(event) => update({ lifecycle: event.target.value })}
                >
                  {["Pre-launch", "Launch", "Established brand", "Loss of exclusivity"].map(
                    (value) => (
                      <option key={value}>{value}</option>
                    ),
                  )}
                </select>
              </label>
              <label className="aw-field sp-spaces-form-field">
                <span>Analyst</span>
                <input
                  placeholder="Your name"
                  value={project.owner}
                  maxLength={80}
                  onChange={(event) => update({ owner: event.target.value })}
                />
              </label>
            </div>
          </details>
          <div className="aw-device-note">
            <p>
              {saveState === "saved"
                ? "Saved on this device. Export a review pack to share with your team."
                : "Device storage is unavailable. Export a review pack to keep your changes."}
            </p>
          </div>
        </aside>
        <div className="aw-main">
          <div className="aw-project-heading">
            <div>
              <div className="aw-title-row">
                <h2>{project.name || "Untitled forecast"}</h2>
                <span
                  className={`aw-review-label ${latestReview && !snapshotCurrent ? "changed" : ""}`}
                >
                  {latestReview
                    ? snapshotCurrent
                      ? "Snapshot current"
                      : "Changes to review"
                    : "Draft"}
                </span>
              </div>
              <div className="aw-project-meta">
                {project.sample && <span className="aw-sample">Synthetic sample data</span>}
                {project.mode === "patient" && (
                  <span className="aw-sample">Patient assumptions need review</span>
                )}
                <span>{project.brand || "Asset not assigned"}</span>
                <span>{project.country}</span>
                <span>{project.lifecycle}</span>
              </div>
            </div>
            <div className="aw-actions">
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.json"
                hidden
                onChange={(event) => importFile(event.target.files?.[0])}
              />
              <button className="aw-button" onClick={() => fileRef.current?.click()}>
                <Upload size={16} />
                Import data
              </button>
              <button className="aw-button" disabled={!ready} onClick={saveVersion}>
                <History size={16} />
                Save version
              </button>
              <button
                className="aw-button"
                onClick={() =>
                  download(
                    "forecast-review.json",
                    JSON.stringify(
                      {
                        schema: "corten-forecast-review-v1",
                        exportedAt: new Date().toISOString(),
                        project,
                        output: result.rows,
                      },
                      null,
                      2,
                    ),
                    "application/json",
                  )
                }
              >
                <ArrowDownToLine size={16} />
                Export review pack
              </button>
            </div>
          </div>
          <div className="aw-tabs" role="tablist" aria-label="Forecast workflow">
            {WORKSPACE_TABS.map((label, index) => (
              <button
                role="tab"
                id={`aw-tab-${index}`}
                tabIndex={tab === label ? 0 : -1}
                aria-selected={tab === label}
                aria-controls={label === "Overview" ? "aw-overview" : "aw-tab-panel"}
                key={label}
                className={tab === label ? "active" : ""}
                onClick={() => setTab(label)}
                onKeyDown={(event) => {
                  const next =
                    event.key === "ArrowRight"
                      ? (index + 1) % WORKSPACE_TABS.length
                      : event.key === "ArrowLeft"
                        ? (index + WORKSPACE_TABS.length - 1) % WORKSPACE_TABS.length
                        : event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? WORKSPACE_TABS.length - 1
                            : null;
                  if (next === null) return;
                  event.preventDefault();
                  setTab(WORKSPACE_TABS[next]);
                  document.getElementById(`aw-tab-${next}`)?.focus();
                }}
              >
                {label}
              </button>
            ))}
          </div>
          {tab !== "Pharma updates" && (
            <section className="aw-metrics" aria-label="Forecast summary">
              <div>
                <span>Base net sales</span>
                <strong>{ready ? money(baseTotal) : "—"}</strong>
                <small>{project.horizon}-month planning horizon</small>
              </div>
              <div>
                <span>Scenario range</span>
                <strong className="aw-range">
                  {ready ? `${money(downsideTotal)} – ${money(upsideTotal)}` : "—"}
                </strong>
                <small>Assumed scenarios · not confidence bounds</small>
              </div>
              <div>
                <span>
                  {project.mode === "patient" ? "Active patients at horizon" : "Forecast volume"}
                </span>
                <strong>
                  {ready
                    ? number(
                        project.mode === "patient"
                          ? result.rows.Base.at(-1)?.patients || 0
                          : result.rows.Base.reduce((sum, row) => sum + row.volume, 0),
                      )
                    : "—"}
                </strong>
                <small>
                  {project.mode === "patient"
                    ? "Expected patients · aggregate cohort"
                    : "Total units · baseline"}
                </small>
              </div>
              <div>
                <span>
                  {project.mode === "patient" ? "Monthly discontinuation" : "Backtest WAPE"}
                </span>
                <strong>
                  {project.mode === "patient"
                    ? `${project.patient.discontinuation}%`
                    : bestScore?.wape != null
                      ? `${bestScore.wape.toFixed(1)}%`
                      : "—"}
                </strong>
                <small>
                  {project.mode === "patient"
                    ? "Declared persistence assumption"
                    : `${result.holdout || "No"} held-out months · lower is better`}
                </small>
              </div>
            </section>
          )}
          {tab === "Overview" && (
            <div id="aw-overview" role="tabpanel" aria-labelledby="aw-tab-0">
              <section className="aw-card aw-outlook">
                <div className="aw-card-header">
                  <div>
                    <h3>{project.mode === "patient" ? "Patient outlook" : "Volume outlook"}</h3>
                    <p>
                      {result.selectedModel} <span>·</span>{" "}
                      {project.mode === "patient" ? "Active brand patients" : "Monthly units"}
                    </p>
                  </div>
                  <div className="aw-legend">
                    {project.mode === "historical" && (
                      <span>
                        <i style={{ background: "var(--color-text-secondary)" }} />
                        Historical
                      </span>
                    )}
                    {(Object.keys(COLORS) as ScenarioName[]).map((name) => (
                      <span key={name}>
                        <i style={{ background: COLORS[name] }} />
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
                <ForecastChart project={project} rows={result.rows} />
                <div className="aw-chart-footer">
                  <span>
                    {ready
                      ? `${month(result.rows.Base[0].date)} – ${month(result.rows.Base.at(-1)!.date)}`
                      : "Waiting for data"}
                  </span>
                  <label>
                    Horizon
                    <select
                      aria-label="Forecast horizon"
                      value={project.horizon}
                      onChange={(event) => update({ horizon: Number(event.target.value) })}
                    >
                      {Array.from(new Set([3, 6, 12, 24, 36, project.horizon]))
                        .sort((a, b) => a - b)
                        .map((value) => (
                          <option key={value} value={value}>
                            {value} months
                          </option>
                        ))}
                    </select>
                  </label>
                </div>
              </section>
              <div className="aw-overview-grid">
                <section className="aw-card aw-summary-card">
                  <div className="aw-section-heading">
                    <h3>Planning assumptions</h3>
                    <button className="aw-text-button" onClick={() => setTab("Model inputs")}>
                      Edit inputs
                    </button>
                  </div>
                  <dl className="aw-assumption-list">
                    <div>
                      <dt>Forecast approach</dt>
                      <dd>{project.mode === "patient" ? "Patient-based" : "Historical trend"}</dd>
                    </div>
                    <div>
                      <dt>Selected baseline</dt>
                      <dd>{result.selectedModel}</dd>
                    </div>
                    <div>
                      <dt>Gross unit price</dt>
                      <dd>
                        {new Intl.NumberFormat("en", {
                          style: "currency",
                          currency: project.currency,
                          maximumFractionDigits: 2,
                        }).format(project.price)}
                      </dd>
                    </div>
                    <div>
                      <dt>Gross-to-net deduction</dt>
                      <dd>{project.g2n}%</dd>
                    </div>
                    <div>
                      <dt>Forecast owner</dt>
                      <dd>{project.owner || "Not assigned"}</dd>
                    </div>
                  </dl>
                  <p className="aw-method-note">
                    {project.sample
                      ? "Sample data is illustrative. Import your approved data before planning."
                      : "Scenario ranges reflect supplied assumptions, not prediction intervals."}
                  </p>
                </section>
                <section className="aw-card aw-summary-card">
                  <div className="aw-section-heading">
                    <h3>Prepare for review</h3>
                    <span className="aw-review-count">
                      {reviewTasks.filter((task) => task.done).length} / {reviewTasks.length}
                    </span>
                  </div>
                  <div className="aw-review-tasks">
                    {reviewTasks.map((task) => (
                      <button key={task.label} onClick={task.action}>
                        <span
                          className={`aw-task-state ${task.done ? "complete" : ""}`}
                          aria-label={task.done ? "Completed" : "Needs attention"}
                        >
                          {task.done ? <Check size={14} /> : <span />}
                        </span>
                        <span>
                          <strong>{task.label}</strong>
                          <small>{task.detail}</small>
                        </span>
                        <ChevronDown size={14} className="aw-task-arrow" />
                      </button>
                    ))}
                  </div>
                  <p className="aw-method-note">
                    Preparation checklist. Final review takes place with your team.
                  </p>
                </section>
              </div>
            </div>
          )}
          {tab !== "Overview" && (
            <section
              className="aw-card aw-tab-panel"
              role="tabpanel"
              id="aw-tab-panel"
              aria-labelledby={`aw-tab-${WORKSPACE_TABS.indexOf(tab)}`}
            >
              {tab === "Pharma updates" && (
                <PharmaUpdates
                  onUseAsEvidence={(item) => {
                    setEvidenceTitle(item.title.slice(0, 160));
                    setEvidenceURL(item.url);
                    setEvidenceRationale("");
                    setTab("Evidence & review");
                    setNotice(
                      "Source selected. Explain the assumption it supports, then add evidence.",
                    );
                  }}
                />
              )}
              {tab === "Model inputs" && (
                <>
                  <div className="aw-section-heading">
                    <div>
                      <h3>Build your baseline</h3>
                      <p>Choose the model that fits the asset and available evidence.</p>
                    </div>
                    <div className="aw-mode-switch">
                      <button
                        className={project.mode === "historical" ? "active" : ""}
                        onClick={() => update({ mode: "historical" })}
                      >
                        Historical trend
                      </button>
                      <button
                        className={project.mode === "patient" ? "active" : ""}
                        onClick={() => update({ mode: "patient" })}
                      >
                        Patient-based
                      </button>
                    </div>
                  </div>
                  {project.mode === "historical" ? (
                    <>
                      <div
                        className="aw-upload"
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                          event.preventDefault();
                          importFile(event.dataTransfer.files[0]);
                        }}
                      >
                        <span className="aw-upload-icon">
                          <Upload size={21} />
                        </span>
                        <div>
                          <strong>
                            {project.series.length
                              ? `${project.series.length} validated monthly observations`
                              : "Bring in your monthly volume data"}
                          </strong>
                          <p>
                            {project.series.length
                              ? `${month(project.series[0].date)} to ${month(project.series.at(-1)!.date)} · one observation per month`
                              : "CSV with date,value columns. At least 12 consecutive months."}
                          </p>
                        </div>
                        <button className="aw-button" onClick={() => fileRef.current?.click()}>
                          Choose file
                        </button>
                      </div>
                      <div className="aw-inline-actions">
                        <button
                          onClick={() =>
                            download(
                              "monthly-volume-template.csv",
                              "date,value\n" +
                                SAMPLE_SERIES.map((row) => `${row.date},${row.value}`).join("\n"),
                              "text/csv",
                            )
                          }
                        >
                          Download sample CSV <ArrowDownToLine size={12} />
                        </button>
                        <span>Aggregate volume only; use YYYY-MM dates.</span>
                      </div>
                      <div className="aw-fields aw-fields-three">
                        <label className="aw-field sp-spaces-form-field">
                          <span>Forecast method</span>
                          <select
                            value={project.model}
                            onChange={(event) =>
                              update({ model: event.target.value as ForecastProject["model"] })
                            }
                          >
                            <option value="auto">Auto · lowest holdout MAE</option>
                            <option value="trend">Linear trend</option>
                            <option value="average">Recent average</option>
                            <option value="seasonal" disabled={project.series.length < 12}>
                              Seasonal naive
                            </option>
                          </select>
                        </label>
                        <NumericField
                          label="Gross unit price"
                          value={project.price}
                          onChange={(value) => update({ price: value })}
                          suffix={project.currency}
                        />
                        <NumericField
                          label="Gross-to-net deduction"
                          value={project.g2n}
                          max={100}
                          onChange={(value) => update({ g2n: value })}
                          suffix="%"
                        />
                      </div>
                      {result.scores.length > 0 && (
                        <div className="aw-table-wrap">
                          <table>
                            <thead>
                              <tr>
                                <th>Baseline comparison</th>
                                <th>MAE (units)</th>
                                <th>RMSE (units)</th>
                                <th>WAPE</th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.scores.map((score, index) => (
                                <tr key={score.id}>
                                  <td>
                                    {score.label}
                                    {index === 0 && (
                                      <span className="aw-best">
                                        <Check size={11} />
                                        Best holdout MAE
                                      </span>
                                    )}
                                  </td>
                                  <td>{number(score.mae)}</td>
                                  <td>{number(score.rmse)}</td>
                                  <td>
                                    {score.wape == null
                                      ? "Not defined"
                                      : `${score.wape.toFixed(1)}%`}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <p className="aw-method-note">
                            Last {result.holdout} months held out chronologically; selected model
                            refitted on all history. These are simple statistical baselines, not
                            validated enterprise models.
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="aw-model-note">
                        <p>
                          A transparent patient-flow planning baseline. Defaults are illustrative;
                          validate assumptions and link evidence before a team review.
                        </p>
                      </div>
                      <div className="aw-input-group">
                        <h4>Population and access</h4>
                        <div className="aw-fields aw-fields-two">
                          <NumericField
                            label="Existing prevalent population"
                            value={project.patient.existingPatients}
                            onChange={(value) => updatePatient("existingPatients", value)}
                            hint="Before diagnosis and eligibility filters"
                          />
                          <NumericField
                            label="Annual incident patients"
                            value={project.patient.annualIncidence}
                            onChange={(value) => updatePatient("annualIncidence", value)}
                          />
                          <NumericField
                            label="Diagnosis rate"
                            value={project.patient.diagnosis}
                            max={100}
                            suffix="%"
                            onChange={(value) => updatePatient("diagnosis", value)}
                          />
                          <NumericField
                            label="Treatment eligibility"
                            value={project.patient.eligibility}
                            max={100}
                            suffix="%"
                            onChange={(value) => updatePatient("eligibility", value)}
                          />
                        </div>
                      </div>
                      <div className="aw-input-group">
                        <h4>Treatment and brand uptake</h4>
                        <div className="aw-fields aw-fields-three">
                          <NumericField
                            label="Monthly treatment initiation"
                            value={project.patient.initiation}
                            max={100}
                            suffix="%"
                            onChange={(value) => updatePatient("initiation", value)}
                            hint="Proportion of the untreated eligible pool"
                          />
                          <NumericField
                            label="Brand capture among initiators"
                            value={project.patient.capture}
                            max={100}
                            suffix="%"
                            onChange={(value) => updatePatient("capture", value)}
                          />
                          <NumericField
                            label="Monthly discontinuation"
                            value={project.patient.discontinuation}
                            max={100}
                            suffix="%"
                            onChange={(value) => updatePatient("discontinuation", value)}
                          />
                          <NumericField
                            label="Launch ramp"
                            value={project.patient.rampMonths}
                            min={1}
                            max={60}
                            suffix="months"
                            onChange={(value) => updatePatient("rampMonths", value)}
                          />
                          <NumericField
                            label="Units per active patient / month"
                            value={project.patient.unitsPerPatient}
                            onChange={(value) => updatePatient("unitsPerPatient", value)}
                          />
                        </div>
                      </div>
                      <div className="aw-input-group">
                        <h4>Commercial assumptions</h4>
                        <div className="aw-fields aw-fields-three">
                          <label className="aw-field sp-spaces-form-field">
                            <span>Forecast start</span>
                            <input
                              type="month"
                              min="1900-01"
                              max="2199-12"
                              value={project.startMonth}
                              onChange={(event) => {
                                if (validMonth(event.target.value))
                                  update({ startMonth: event.target.value });
                              }}
                            />
                          </label>
                          <NumericField
                            label="Unit price"
                            value={project.price}
                            suffix={project.currency}
                            onChange={(value) => update({ price: value })}
                          />
                          <NumericField
                            label="Gross-to-net deduction"
                            value={project.g2n}
                            max={100}
                            suffix="%"
                            onChange={(value) => update({ g2n: value })}
                          />
                        </div>
                      </div>
                      <details className="aw-formula">
                        <summary>How the patient-flow model works</summary>
                        <p>
                          Eligible untreated patients receive monthly incident inflow. Treatment
                          initiation reduces that pool. Brand starts depend on capture and a linear
                          launch ramp. Active patients carry forward after discontinuation. Units =
                          active patients × units per patient; net sales = units × price × (1 −
                          gross-to-net deduction). This simplified model does not represent
                          treatment lines, competitor cohorts, switching, mortality, or clinical
                          outcomes.
                        </p>
                      </details>
                    </>
                  )}
                  <label className="aw-field sp-spaces-form-field aw-currency">
                    <span>Reporting currency · no FX conversion</span>
                    <select
                      value={project.currency}
                      onChange={(event) => update({ currency: event.target.value })}
                    >
                      {["USD", "EUR", "GBP", "INR"].map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </select>
                  </label>
                </>
              )}
              {tab === "Scenarios" && (
                <>
                  <div className="aw-section-heading">
                    <div>
                      <h3>Make uncertainty explicit</h3>
                      <p>
                        Relative changes from the baseline. Assumed scenarios, not prediction
                        intervals.
                      </p>
                    </div>
                  </div>
                  <div className="aw-scenario-grid">
                    {(["Upside", "Downside"] as const).map((name) => {
                      const volumeKey = name === "Upside" ? "upsideVolume" : "downsideVolume",
                        priceKey = name === "Upside" ? "upsidePrice" : "downsidePrice";
                      return (
                        <div className="aw-scenario-card" key={name}>
                          <h4>
                            <i style={{ background: COLORS[name] }} />
                            {name}
                          </h4>
                          <label>
                            {project.mode === "patient" ? "Brand capture change" : "Volume change"}
                            <strong>
                              {project.scenarios[volumeKey] > 0 ? "+" : ""}
                              {project.scenarios[volumeKey]}%
                            </strong>
                            <input
                              aria-label={`${name} volume change`}
                              type="range"
                              min={name === "Upside" ? 0 : -60}
                              max={name === "Upside" ? 60 : 0}
                              value={project.scenarios[volumeKey]}
                              onChange={(event) =>
                                update({
                                  scenarios: {
                                    ...project.scenarios,
                                    [volumeKey]: Number(event.target.value),
                                  },
                                })
                              }
                            />
                          </label>
                          <NumericField
                            label="Unit price change"
                            min={name === "Upside" ? 0 : -60}
                            max={name === "Upside" ? 60 : 0}
                            value={project.scenarios[priceKey]}
                            suffix="%"
                            onChange={(value) =>
                              update({ scenarios: { ...project.scenarios, [priceKey]: value } })
                            }
                          />
                          <div className="aw-scenario-total">
                            <span>Forecast net sales</span>
                            <strong>{money(total(result.rows[name]))}</strong>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="aw-event">
                    <div>
                      <h4>Market event overlay</h4>
                      <p>
                        Affect {project.mode === "patient" ? "brand capture" : "volume"} from the
                        chosen forecast month onward, across all scenarios.
                      </p>
                    </div>
                    <div className="aw-fields aw-fields-three">
                      <label className="aw-field sp-spaces-form-field">
                        <span>Event / rationale</span>
                        <input
                          placeholder="e.g. competitor entry or access change"
                          maxLength={180}
                          value={project.scenarios.eventName}
                          onChange={(event) =>
                            update({
                              scenarios: { ...project.scenarios, eventName: event.target.value },
                            })
                          }
                        />
                      </label>
                      <NumericField
                        label="First affected forecast month"
                        integer
                        value={project.scenarios.eventMonth}
                        min={1}
                        max={60}
                        hint={
                          project.scenarios.eventMonth > project.horizon
                            ? "This event is outside the current horizon and does not affect these outputs."
                            : "Counted from the first forecast month."
                        }
                        onChange={(value) =>
                          update({
                            scenarios: { ...project.scenarios, eventMonth: value },
                          })
                        }
                      />
                      <NumericField
                        label="Relative event impact"
                        value={project.scenarios.eventImpact}
                        min={-100}
                        max={100}
                        suffix="%"
                        onChange={(value) =>
                          update({ scenarios: { ...project.scenarios, eventImpact: value } })
                        }
                      />
                    </div>
                  </div>
                </>
              )}
              {tab === "Evidence & review" && (
                <>
                  <div className="aw-section-heading">
                    <div>
                      <h3>Keep the reasoning with the numbers</h3>
                      <p>Record sources, assumption rationale, and review versions.</p>
                    </div>
                  </div>
                  <div className="aw-fields aw-fields-two">
                    <label className="aw-field sp-spaces-form-field">
                      <span>Evidence title</span>
                      <input
                        placeholder="e.g. analog launch uptake study"
                        value={evidenceTitle}
                        maxLength={160}
                        onChange={(event) => setEvidenceTitle(event.target.value)}
                      />
                    </label>
                    <label className="aw-field sp-spaces-form-field">
                      <span>Source URL · optional</span>
                      <input
                        type="url"
                        placeholder="https://… or leave blank for internal evidence"
                        value={evidenceURL}
                        maxLength={500}
                        onChange={(event) => setEvidenceURL(event.target.value)}
                      />
                    </label>
                  </div>
                  <label className="aw-field sp-spaces-form-field">
                    <span>Assumption supported / rationale</span>
                    <textarea
                      placeholder="Which input does this support, and what should reviewers check?"
                      value={evidenceRationale}
                      maxLength={2000}
                      onChange={(event) => setEvidenceRationale(event.target.value)}
                    />
                  </label>
                  <button className="aw-button" onClick={addEvidence}>
                    <Plus size={14} />
                    Add evidence
                  </button>
                  <div className="aw-evidence-list">
                    {project.evidence.map((item) => (
                      <article key={item.id}>
                        <FileText size={17} />
                        <div>
                          <strong>{item.title}</strong>
                          <p>{item.rationale}</p>
                          {safeURL(item.url) && (
                            <a href={safeURL(item.url)} target="_blank" rel="noopener noreferrer">
                              Open source <ArrowUpRight size={12} />
                            </a>
                          )}
                          <small>Added {reviewDate(item.addedAt)}</small>
                        </div>
                        <button
                          aria-label={`Remove evidence ${item.title}`}
                          onClick={() =>
                            update({ evidence: project.evidence.filter((e) => e.id !== item.id) })
                          }
                        >
                          <X size={14} />
                        </button>
                      </article>
                    ))}
                    {!project.evidence.length && (
                      <p className="aw-method-note">
                        No evidence linked yet. The sample data and patient defaults are
                        illustrative.
                      </p>
                    )}
                  </div>
                  <label className="aw-field sp-spaces-form-field">
                    <span>Analyst notes / review questions</span>
                    <textarea
                      placeholder="Document assumptions, changes, open questions, and the decision needed."
                      value={project.notes}
                      maxLength={12000}
                      onChange={(event) => update({ notes: event.target.value })}
                    />
                  </label>
                  <div className="aw-version-heading">
                    <h4>Review versions</h4>
                    <button className="aw-button" disabled={!ready} onClick={saveVersion}>
                      <Plus size={13} />
                      Save current version
                    </button>
                  </div>
                  {project.versions
                    .slice()
                    .reverse()
                    .map((version) => (
                      <div className="aw-version" key={version.id}>
                        <History size={16} />
                        <span>
                          <strong>{version.name}</strong>
                          <small>
                            {reviewDate(version.savedAt, true)} ·{" "}
                            {version.inputs.owner || "Analyst not assigned"}
                          </small>
                        </span>
                        <span>{money(total(version.rows.Base), version.inputs.currency)}</span>
                        <button
                          className="aw-button"
                          onClick={() =>
                            download(
                              "forecast-version.json",
                              JSON.stringify(
                                {
                                  schema: "corten-forecast-review-v1",
                                  project: { ...version.inputs, versions: [] },
                                  output: version.rows,
                                },
                                null,
                                2,
                              ),
                              "application/json",
                            )
                          }
                        >
                          <ArrowDownToLine size={13} />
                          Export
                        </button>
                      </div>
                    ))}
                  <p className="aw-method-note">
                    Versions are local snapshots for review handoff, not authenticated approvals or
                    a shared audit trail.
                  </p>
                </>
              )}
              {tab === "Monthly outputs" && (
                <>
                  <div className="aw-section-heading">
                    <div>
                      <h3>Monthly planning outputs</h3>
                      <p>Baseline values. Export includes all three scenarios.</p>
                    </div>
                    <button
                      className="aw-button"
                      disabled={!ready}
                      onClick={() =>
                        download("forecast-monthly.csv", exportCSV(result.rows), "text/csv")
                      }
                    >
                      <ArrowDownToLine size={14} />
                      Export CSV
                    </button>
                  </div>
                  <div className="aw-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Month</th>
                          {project.mode === "patient" && (
                            <>
                              <th>New brand starts</th>
                              <th>Active patients</th>
                            </>
                          )}
                          <th>Units</th>
                          <th>Gross sales ({project.currency})</th>
                          <th>Net sales ({project.currency})</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.rows.Base.map((row) => (
                          <tr key={row.date}>
                            <td>{month(row.date)}</td>
                            {project.mode === "patient" && (
                              <>
                                <td>{number(row.starts || 0)}</td>
                                <td>{number(row.patients || 0)}</td>
                              </>
                            )}
                            <td>{number(row.volume)}</td>
                            <td>{money(row.grossSales)}</td>
                            <td>{money(row.netSales)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!ready && (
                      <p className="aw-method-note">
                        Import historical volume or configure a patient model to generate outputs.
                      </p>
                    )}
                  </div>
                </>
              )}
            </section>
          )}
          <section className="aw-copilot">
            <div>
              <h3>Analyst assistance</h3>
              <p>
                Explain calculated results, or research external drivers before changing
                assumptions.
              </p>
            </div>
            <div className="aw-actions">
              <Link
                className={`aw-button ${!ready ? "disabled" : ""}`}
                aria-disabled={!ready}
                href={ready ? `/search?q=${encodeURIComponent(explanation)}&focus=writing` : "#"}
                onClick={(event) => {
                  if (!ready) event.preventDefault();
                }}
              >
                <Sparkles size={14} />
                Explain forecast
              </Link>
              <Link
                className="aw-button"
                href={`/search?q=${encodeURIComponent(`Research recent commercial forecasting drivers for ${project.therapy} therapies in ${project.country}: competitor launches, market access changes, and regulatory developments. Cite dated sources; distinguish facts from assumptions.`)}`}
              >
                <Search size={14} />
                Research drivers
              </Link>
            </div>
            <small>
              Explain sends the displayed forecast summary to the AI provider. Research uses web
              sources; neither action changes your model.
            </small>
          </section>
        </div>
      </div>
    </div>
  );
}
