"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  ChartNoAxesCombined,
  Check,
  ChevronDown,
  Download,
  FileSpreadsheet,
  Info,
  LoaderCircle,
  ShieldCheck,
  Table2,
  Upload,
  X,
} from "lucide-react";
import { displayValue, saveDownload } from "@/lib/interpolationDisplay";
import CurveChart from "./CurveChart";
import InterpolationGuide from "./InterpolationGuide";
import {
  interpolationService,
  type CsvEncoding,
  type InputPreview,
  type InterpolationMode,
  type InterpolationResult,
} from "@/services/interpolationService";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
type Tab = "monthly" | "yearly" | "checks";

export default function YearlyMonthlyWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [encoding, setEncoding] = useState<CsvEncoding>("auto");
  const [mode, setMode] = useState<InterpolationMode>("average");
  const [preview, setPreview] = useState<InputPreview | null>(null);
  const [result, setResult] = useState<InterpolationResult | null>(null);
  const [status, setStatus] = useState<"idle" | "reading" | "calculating" | "exporting">("idle");
  const [error, setError] = useState("");
  const [column, setColumn] = useState(0);
  const [year, setYear] = useState(0);
  const [tab, setTab] = useState<Tab>("monthly");
  const [precision, setPrecision] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [showAllInput, setShowAllInput] = useState(false);
  const [notice, setNotice] = useState("");
  const [exportFormat, setExportFormat] = useState<"csv" | "json" | "pdf" | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const resultsPanel = useRef<HTMLDivElement>(null);
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const busy = status !== "idle";

  useEffect(
    () => () => {
      generation.current++;
      active.current?.abort();
    },
    [],
  );
  useEffect(() => {
    if (result && window.matchMedia("(max-width: 1050px)").matches) {
      resultsPanel.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
    }
  }, [result]);
  const begin = () => {
    generation.current++;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    return { id: generation.current, controller };
  };
  const clearResult = () => {
    setResult(null);
    setColumn(0);
    setYear(0);
    setTab("monthly");
    setNotice("");
    setExportFormat(null);
  };
  const readFile = async (selected: File, selectedEncoding = encoding) => {
    const { id, controller } = begin();
    setFile(selected);
    setPreview(null);
    clearResult();
    setShowAllInput(false);
    setError("");
    setStatus("reading");
    try {
      if (!/\.csv$/i.test(selected.name)) throw new Error("Choose a file with a .csv extension.");
      if (selected.size > 10 * 1024 * 1024)
        throw new Error("CSV files must be no larger than 10 MB.");
      const parsed = await interpolationService.preview(
        selected,
        selectedEncoding,
        controller.signal,
      );
      if (generation.current === id) setPreview(parsed);
    } catch (failure) {
      if (generation.current === id && !controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : "Unable to read this CSV.");
    } finally {
      if (generation.current === id) setStatus("idle");
    }
  };
  const changeMode = (next: InterpolationMode) => {
    if (mode === next) return;
    if (status === "reading") {
      setMode(next);
      return;
    }
    begin();
    setMode(next);
    clearResult();
    setError("");
    setStatus("idle");
  };
  const generate = async () => {
    if (!file || !preview) return;
    const { id, controller } = begin();
    setStatus("calculating");
    setError("");
    clearResult();
    try {
      const calculated = await interpolationService.calculate(
        file,
        encoding,
        mode,
        controller.signal,
      );
      if (generation.current === id) setResult(calculated);
    } catch (failure) {
      if (generation.current === id && !controller.signal.aborted)
        setError(
          failure instanceof Error
            ? failure.message
            : "Unable to calculate a reliable monthly series.",
        );
    } finally {
      if (generation.current === id) setStatus("idle");
    }
  };
  const exportResult = async (format: "csv" | "json" | "pdf") => {
    if (!file || !result) return;
    const { id, controller } = begin();
    setStatus("exporting");
    setExportFormat(format);
    setError("");
    setNotice("");
    try {
      const blob = await interpolationService.export(
        file,
        encoding,
        result,
        format,
        controller.signal,
      );
      if (generation.current === id) {
        saveDownload(blob, `monthly-${result.mode}.${format}`);
        setNotice(`${format.toUpperCase()} download is ready.`);
      }
    } catch (failure) {
      if (generation.current === id && !controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : "Unable to export this result.");
    } finally {
      if (generation.current === id) {
        setStatus("idle");
        setExportFormat(null);
      }
    }
  };
  const shownInput = result || preview;
  const timeline = shownInput ? shownInput.yearly.length === 1
    ? String(shownInput.yearly[0].year)
    : `${shownInput.yearly[0].year}–${shownInput.yearly.at(-1)?.year}` : "";
  const series = result?.series[column];
  const monthly = useMemo(
    () => result?.monthly.filter((row) => row.year === result.yearly[year]?.year) || [],
    [result, year],
  );
  const checks = result?.checks.filter((check) => check.column === column) || [];
  const outside = result?.series.filter((item) => item.outside_range_months > 0) || [];
  const verified = result?.checks.filter(check => check.passed).length || 0;
  const stage = result ? 3 : preview ? 2 : 1;
  const tabs = [
    ["monthly", "Monthly values"],
    ["yearly", "Yearly input"],
    ["checks", "Validation"],
  ] as const;

  return (
    <div className="aw-tool aw-interpolation">
      <div className="aw-tool-heading">
        <div>
          <h2>Monthly interpolation</h2>
        </div>
        <ol className="aw-workflow" aria-label="Analysis progress">
          {["Input", "Calculate", "Review"].map((label, index) => (
            <li
              key={label}
              data-state={
                stage > index + 1 ? "complete" : stage === index + 1 ? "active" : "pending"
              }
              aria-current={stage === index + 1 ? "step" : undefined}
            >
              <span>{stage > index + 1 ? <Check size={12} aria-hidden="true" /> : index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
      </div>
      <div className="aw-tool-layout">
        <aside className="aw-input-panel" aria-label="Interpolation setup">
          <div className="mi-setup-intro">
            <span className="mi-panel-icon"><FileSpreadsheet size={18} strokeWidth={1.5} aria-hidden="true" /></span>
            <div><h3>Setup</h3></div>
          </div>
          <section className="aw-setup-section" aria-labelledby="aw-input-title">
            <div className="aw-section-title">
              <span>01</span>
              <h3 id="aw-input-title">Yearly input</h3>
            </div>
            <input
              ref={input}
              id="aw-csv-upload"
              className="sr-only"
              type="file"
              tabIndex={-1}
              accept=".csv,text/csv"
              aria-label="Upload yearly CSV"
              onChange={(event) => {
                const selected = event.target.files?.[0];
                if (selected) void readFile(selected);
                event.target.value = "";
              }}
            />
            <button
              className={`aw-upload-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
              type="button"
              onClick={() => input.current?.click()}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                if (event.dataTransfer.files.length !== 1) {
                  setError(
                    "Upload one CSV file at a time. Put independent series in separate columns of the same file.",
                  );
                  return;
                }
                const selected = event.dataTransfer.files[0];
                if (selected) void readFile(selected);
              }}
            >
              <span className="aw-upload-icon">
                <Upload size={20} strokeWidth={1.5} />
              </span>
              <strong>{file ? "Replace CSV" : "Upload CSV"}</strong>
              <span>Browse or drop a file · Max 10 MB</span>
            </button>
            {file && (
              <div className="aw-selected-file">
                {status === "reading" ? (
                  <LoaderCircle size={18} className="aw-spin" />
                ) : (
                  <FileSpreadsheet size={18} />
                )}
                <div>
                  <strong title={file.name}>{file.name}</strong>
                  <span>
                    {preview
                      ? `${preview.yearly.length} ${preview.yearly.length === 1 ? "year" : "years"} · ${preview.columns.length} series`
                      : status === "reading"
                        ? "Reading input…"
                        : "Input needs attention"}
                  </span>
                </div>
                <button
                  aria-label="Remove uploaded file"
                  onClick={() => {
                    begin();
                    setFile(null);
                    setPreview(null);
                    clearResult();
                    setStatus("idle");
                    setError("");
                  }}
                >
                  <X size={16} />
                </button>
              </div>
            )}
            <p className="aw-help">
              One <code>year</code> column and one or more value columns.
            </p>
            <a className="aw-example-link" href="/examples/yearly-adoption-example.csv" download>
              <Download size={13} />
              Sample CSV
            </a>
            <details className="aw-encoding">
              <summary>
                CSV format &amp; encoding
                <ChevronDown size={13} />
              </summary>
              <p className="aw-help">Calendar and relative years are supported. <code>25%</code> and <code>25</code> both mean 25. Common Excel encodings are detected automatically.</p>
              <label htmlFor="aw-encoding-select">File encoding</label>
              <select
                id="aw-encoding-select"
                value={encoding}
                onChange={(event) => {
                  const next = event.target.value as CsvEncoding;
                  setEncoding(next);
                  if (file) void readFile(file, next);
                }}
              >
                <option value="auto">Auto · UTF-8 / UTF-16 / Windows</option>
                <option value="utf-8-sig">UTF-8 (with or without BOM)</option>
                <option value="utf-16">UTF-16 (Excel Unicode)</option>
                <option value="cp1252">Windows-1252</option>
                <option value="gb18030">GB18030 (Chinese CSV)</option>
              </select>
            </details>
          </section>
          <section className="aw-setup-section" aria-labelledby="aw-mode-title">
            <div className="aw-section-title aw-mode-heading">
              <span>02</span>
              <h3 id="aw-mode-title">Calculation mode</h3>
            </div>
            <div
              className="aw-mode-options"
              role="radiogroup"
              aria-label="Calculation mode"
              onKeyDown={(event) => {
                if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
                  event.preventDefault();
                  const next = mode === "average" ? "exit" : "average";
                  changeMode(next);
                  document.getElementById(`aw-mode-${next}`)?.focus();
                }
              }}
            >
              <button
                id="aw-mode-average"
                role="radio"
                tabIndex={mode === "average" ? 0 : -1}
                aria-checked={mode === "average"}
                className={`aw-mode-option ${mode === "average" ? "selected" : ""}`}
                onClick={() => changeMode("average")}
              >
                <span className="aw-radio-dot" />
                <div>
                  <strong>Average</strong>
                  <small className="mi-mode-rule">12-month mean = yearly target</small>
                </div>
              </button>
              <button
                id="aw-mode-exit"
                role="radio"
                tabIndex={mode === "exit" ? 0 : -1}
                aria-checked={mode === "exit"}
                className={`aw-mode-option ${mode === "exit" ? "selected" : ""}`}
                onClick={() => changeMode("exit")}
              >
                <span className="aw-radio-dot" />
                <div>
                  <strong>Exit</strong>
                  <small className="mi-mode-rule">December = yearly target</small>
                </div>
              </button>
            </div>
            <button
              id="aw-generate"
              className="aw-generate"
              onClick={() => void generate()}
              disabled={!preview || busy}
            >
              {status === "calculating" || status === "reading" ? (
                <LoaderCircle className="aw-spin" size={17} />
              ) : (
                <ArrowRight size={17} />
              )}
              {status === "calculating"
                ? "Calculating…"
                : status === "reading"
                  ? "Reading CSV…"
                  : "Generate monthly series"}
            </button>
          </section>
          <p className="aw-data-note">Files are not saved. Download results to keep them.</p>
        </aside>
        <div className="aw-results" ref={resultsPanel} aria-busy={busy}>
          {error && (
            <div className="aw-error" role="alert">
              <div className="aw-error-heading">
                <strong>Unable to complete this step</strong>
                <button
                  className="aw-dismiss-error"
                  aria-label="Dismiss message"
                  onClick={() => setError("")}
                >
                  <X size={16} />
                </button>
              </div>
              <p>{error}</p>
              {file && !result && (
                <button
                  disabled={busy}
                  onClick={() => {
                    if (preview) void generate();
                    else void readFile(file);
                  }}
                >
                  Try again
                  <ArrowRight size={13} />
                </button>
              )}
            </div>
          )}
          <p className="aw-operation-status" role="status" aria-live="polite">
            {status === "exporting" ? `Preparing ${exportFormat?.toUpperCase()} download…` : notice}
          </p>
          {!result && (
            <section
              key={status === "calculating" ? "calculating" : preview?.input_digest || "empty"}
              className={`aw-empty-state aw-stage-enter ${preview ? "mi-preview-state" : "mi-start-state"} ${status === "calculating" ? "aw-calculating" : ""}`}
              aria-live="polite"
            >
              {!preview && status === "idle" && <InterpolationGuide />}
              {(preview || status !== "idle") && <div className="aw-state-icon">
                {status === "calculating" || status === "reading" ? (
                  <LoaderCircle className="aw-spin" size={24} strokeWidth={1.5} />
                ) : preview ? (
                  <Check size={24} strokeWidth={1.5} />
                ) : (
                  <FileSpreadsheet size={24} strokeWidth={1.5} />
                )}
              </div>}
              {(preview || status !== "idle") && <h3>
                {status === "calculating"
                  ? "Calculating…"
                  : status === "reading"
                    ? "Reading CSV…"
                    : preview
                      ? "Input ready"
                      : ""}
              </h3>}
              {status === "calculating" && (
                <div className="aw-loading-preview" aria-hidden="true">
                  <div className="aw-loading-grid" />
                  <div className="aw-loading-sweep" />
                </div>
              )}
              {preview && status !== "calculating" && (
                <div className="aw-input-preview">
                  <div className="mi-preview-heading">
                    <div><h4>Review your yearly input</h4><p>Original values · {timeline}</p></div>
                    <span className="mi-ready-badge"><Check size={13} aria-hidden="true" /> Input checked</span>
                  </div>
                  <dl className="mi-input-summary">
                    <div><dt>Years</dt><dd>{preview.yearly.length}</dd></div>
                    <div><dt>Value columns</dt><dd>{preview.columns.length}</dd></div>
                    <div><dt>Expected monthly rows</dt><dd>{preview.yearly.length * 12}</dd></div>
                  </dl>
                  <div className="aw-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">Year</th>
                          {preview.columns.map((name) => (
                            <th scope="col" key={name}>
                              {name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(showAllInput ? preview.yearly : preview.yearly.slice(0, 5)).map((row) => (
                          <tr key={row.year}>
                            <td>{row.year}</td>
                            {row.values.map((value, index) => (
                              <td key={index}>{displayValue(value, true, preview.units[index])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {preview.yearly.length > 5 && (
                    <div className="aw-preview-footer">
                      <p>
                        Showing {showAllInput ? preview.yearly.length : 5} of{" "}
                        {preview.yearly.length} years. All years are included.
                      </p>
                      <button
                        aria-expanded={showAllInput}
                        onClick={() => setShowAllInput((value) => !value)}
                      >
                        {showAllInput ? "Show fewer" : "Review all years"}
                        <ChevronDown size={13} />
                      </button>
                    </div>
                  )}
                  {preview.sorted_input && (
                    <p>Rows have been sorted by year; values are unchanged.</p>
                  )}
                  <div className="mi-ready-footer">
                    <button className="mi-calculate" disabled={busy} onClick={() => void generate()}>Create monthly results <ArrowRight size={14} aria-hidden="true" /></button>
                  </div>
                </div>
              )}
            </section>
          )}
          {result && series && (
            <div className="aw-result-content aw-stage-enter" key={result.calculation_id}>
              <div className="aw-result-header">
                <div>
                  <span className="aw-verified">
                    <Check size={14} />
                    {verified} yearly constraints verified
                  </span>
                  <h3>Monthly results</h3>
                  <p>
                    {result.mode === "average" ? "Average" : "Exit"} mode · {result.monthly.length}{" "}
                    months · {result.columns.length} independent series
                  </p>
                </div>
                <div className="aw-export-buttons" aria-label="Export results">
                  {(["csv", "json", "pdf"] as const).map((format) => (
                    <button
                      key={format}
                      onClick={() => void exportResult(format)}
                      disabled={busy}
                      aria-label={`Download ${format.toUpperCase()}`}
                    >
                      {exportFormat === format ? (
                        <LoaderCircle className="aw-spin" size={14} />
                      ) : (
                        <Download size={14} />
                      )}
                      {format.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <dl className="aw-result-summary">
                <div>
                  <dt><CalendarDays size={15} aria-hidden="true" /> Timeline</dt>
                  <dd>
                    {timeline}
                    <span>
                      {result.yearly.length} {result.yearly.length === 1 ? "year" : "years"}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt><Table2 size={15} aria-hidden="true" /> Monthly rows</dt>
                  <dd>
                    {result.monthly.length}
                    <span>All years included</span>
                  </dd>
                </div>
                <div>
                  <dt><ChartNoAxesCombined size={15} aria-hidden="true" /> Value series</dt>
                  <dd>
                    {result.columns.length}
                    <span>Calculated independently</span>
                  </dd>
                </div>
                <div>
                  <dt><ShieldCheck size={15} aria-hidden="true" /> Yearly checks</dt>
                  <dd>{verified}<span>{verified === result.checks.length ? "All targets verified" : `${result.checks.length - verified} targets need review`}</span></dd>
                </div>
              </dl>
              <div className="aw-chart-panel">
                <div className="mi-chart-title"><div><span>Monthly curve</span><h4 title={series.name}>{series.name}</h4></div><span className="mi-mode-badge">{result.mode === "average" ? "Average" : "Exit"} mode</span></div>
                <div className="aw-chart-header">
                  <label htmlFor="aw-series-select">View series</label>
                  <select
                    id="aw-series-select"
                    value={column}
                    onChange={(event) => setColumn(Number(event.target.value))}
                  >
                    {result.columns.map((name, index) => (
                      <option key={name} value={index}>
                        {name}
                      </option>
                    ))}
                  </select>
                  <span>First month: {displayValue(series.first_month, false, series.unit)}</span>
                </div>
                <CurveChart
                  key={`${result.calculation_id}:${column}`}
                  result={result}
                  column={column}
                />
              </div>
              {outside.length > 0 && (
                <div className="aw-range-note">
                  <Info size={16} aria-hidden="true" />
                  <p>
                    Monthly values extend beyond the yearly input range in {outside.length} series.
                    Smoothing permits overshoot; the results are not clipped.
                  </p>
                  <button
                    onClick={() => {
                      setTab("checks");
                      document
                        .querySelector(".aw-review-panel")
                        ?.scrollIntoView({ block: "nearest" });
                    }}
                  >
                    View validation
                    <ArrowRight size={13} />
                  </button>
                </div>
              )}
              {result.mode === "exit" && result.yearly.length === 1 && (
                <p className="aw-range-note">
                  A single non-negative yearly target uses a flat monthly series.
                </p>
              )}
              <section className="aw-review-panel" aria-label="Review calculated values">
                <div className="mi-review-heading"><h4>Explore the data</h4><span>Monthly values, source targets and validation</span></div>
                <div className="aw-review-toolbar">
                  <div
                    className="aw-review-tabs"
                    role="tablist"
                    aria-label="Review data"
                    onKeyDown={(event) => {
                      if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
                        event.preventDefault();
                        const index = tabs.findIndex(([value]) => value === tab);
                        const next =
                          event.key === "Home"
                            ? 0
                            : event.key === "End"
                              ? tabs.length - 1
                              : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
                                tabs.length;
                        setTab(tabs[next][0]);
                        document.getElementById(`aw-tab-${tabs[next][0]}`)?.focus();
                      }
                    }}
                  >
                    {tabs.map(([value, label]) => (
                      <button
                        key={value}
                        id={`aw-tab-${value}`}
                        role="tab"
                        tabIndex={tab === value ? 0 : -1}
                        aria-selected={tab === value}
                        aria-controls={`aw-panel-${value}`}
                        onClick={() => setTab(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <label className="aw-precision">
                    <input
                      type="checkbox"
                      checked={precision}
                      onChange={(event) => setPrecision(event.target.checked)}
                    />
                    Full precision
                  </label>
                </div>
                <div
                  id={`aw-panel-${tab}`}
                  className="aw-tab-content aw-stage-enter"
                  key={tab}
                  role="tabpanel"
                  tabIndex={0}
                  aria-labelledby={`aw-tab-${tab}`}
                >
                  {tab === "monthly" && (
                    <div className="aw-table-caption">
                      <label htmlFor="aw-year-select">
                        Year
                        <select
                          id="aw-year-select"
                          value={year}
                          onChange={(event) => setYear(Number(event.target.value))}
                        >
                          {result.yearly.map((row, index) => (
                            <option value={index} key={row.year}>
                              {row.year}
                            </option>
                          ))}
                        </select>
                      </label>
                      <span>
                        12 months shown · Exports include all {result.monthly.length} months
                      </span>
                    </div>
                  )}
                  {tab === "yearly" && (
                    <p className="aw-table-caption">
                      Original targets used in this calculation.{" "}
                      {shownInput?.sorted_input
                        ? "Rows are sorted by year; values are unchanged."
                        : "Uploaded values are unchanged."}
                    </p>
                  )}
                  {tab === "checks" && (
                    <p className="aw-table-caption">
                      {result.columns[column]} · Raw{" "}
                      {result.mode === "average" ? "12-month averages" : "December values"} checked
                      before rounding
                    </p>
                  )}
                  {tab === "checks" && (
                    <p className="aw-range-summary">
                      Input range: {displayValue(series.input_min, false, series.unit)}–
                      {displayValue(series.input_max, false, series.unit)}
                      <br />
                      Monthly range: {displayValue(series.monthly_min, false, series.unit)}–
                      {displayValue(series.monthly_max, false, series.unit)} ·{" "}
                      {series.outside_range_months} months outside the input range
                    </p>
                  )}
                  <div className="aw-table-scroll">
                    <table>
                      <caption className="sr-only">
                        {tab === "checks"
                          ? `${result.columns[column]} yearly constraint checks`
                          : tab === "monthly"
                            ? `Monthly values for year ${result.yearly[year].year}`
                            : "Original yearly input values"}
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Year</th>
                          {tab === "monthly" && <th scope="col">Month</th>}
                          {tab === "checks" ? (
                            <>
                              <th scope="col">Yearly target</th>
                              <th scope="col">
                                {result.mode === "average" ? "Monthly average" : "December"}
                              </th>
                              <th scope="col">Absolute error</th>
                              <th scope="col">Result</th>
                            </>
                          ) : (
                            result.columns.map((name, index) => (
                              <th
                                scope="col"
                                className={index === column ? "aw-selected-cell" : undefined}
                                key={name}
                              >
                                {name}
                              </th>
                            ))
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {tab === "checks"
                          ? checks.map((check) => (
                              <tr key={check.year}>
                                <td>{check.year}</td>
                                <td>
                                  {displayValue(check.target, precision, result.units[column])}
                                </td>
                                <td>
                                  {displayValue(check.actual, precision, result.units[column])}
                                </td>
                                <td>
                                  {check.absolute_error === 0
                                    ? "0"
                                    : check.absolute_error.toExponential(2)}
                                </td>
                                <td>
                                  <span className={check.passed ? "aw-check-pass" : "mi-check-fail"}>
                                    {check.passed ? <Check size={12} /> : <Info size={12} />}
                                    {check.passed ? "Verified" : "Review required"}
                                  </span>
                                </td>
                              </tr>
                            ))
                          : (tab === "monthly" ? monthly : result.yearly).map((row) => (
                              <tr key={`${row.year}:${"month" in row ? row.month : "year"}`}>
                                <td>{row.year}</td>
                                {"month" in row && <td>{MONTHS[(row.month as number) - 1]}</td>}
                                {row.values.map((value, index) => (
                                  <td
                                    className={index === column ? "aw-selected-cell" : undefined}
                                    key={index}
                                  >
                                    {displayValue(
                                      value,
                                      precision || tab === "yearly",
                                      result.units[index],
                                    )}
                                  </td>
                                ))}
                              </tr>
                            ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <p className="aw-rounding-note">
                  {precision
                    ? "Showing full precision."
                    : "Monthly values display two decimal places (scientific notation for very large or small values)."}{" "}
                  Validation, CSV and JSON use unrounded values.
                </p>
              </section>
              <details className="aw-method">
                <summary>
                  How the calculation works
                  <ChevronDown size={15} />
                </summary>
                <p>
                  {result.mode === "average"
                    ? "The curve minimizes month-to-month curvature while enforcing each year's average. Moving beyond each series' yearly minimum or maximum has a soft penalty. The first month has a positive lower bound based on the series scale."
                    : "The curve minimizes month-to-month curvature across the complete timeline, with every December fixed to its yearly input and the first month constrained to be non-negative."}
                </p>
                <p>
                  Every column is calculated independently. Only the first month has a sign
                  constraint; other monthly values may be negative or exceed the input range. %
                  values are retained in their original units.
                </p>
                <p>
                  These are interpolated inputs; they do not incorporate new market evidence or
                  predict demand.
                </p>
              </details>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
