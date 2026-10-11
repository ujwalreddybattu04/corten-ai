export type ForecastMode = "historical" | "patient";
export type ModelId = "auto" | "trend" | "average" | "seasonal";
export interface Observation {
  date: string;
  value: number;
}
export interface PatientInputs {
  existingPatients: number;
  annualIncidence: number;
  diagnosis: number;
  eligibility: number;
  initiation: number;
  capture: number;
  discontinuation: number;
  rampMonths: number;
  unitsPerPatient: number;
}
export interface ScenarioInputs {
  upsideVolume: number;
  downsideVolume: number;
  upsidePrice: number;
  downsidePrice: number;
  eventMonth: number;
  eventImpact: number;
  eventName: string;
}
export interface Evidence {
  id: string;
  title: string;
  url: string;
  rationale: string;
  addedAt: string;
}
export interface ForecastRow {
  date: string;
  volume: number;
  patients: number | null;
  starts: number | null;
  grossSales: number;
  netSales: number;
}
export interface ModelScore {
  id: Exclude<ModelId, "auto">;
  label: string;
  mae: number;
  rmse: number;
  wape: number | null;
}
export interface ReviewVersion {
  id: string;
  savedAt: string;
  name: string;
  inputs: Omit<ForecastProject, "versions">;
  rows: Record<ScenarioName, ForecastRow[]>;
}
export interface ForecastProject {
  id: string;
  name: string;
  brand: string;
  therapy: string;
  country: string;
  owner: string;
  currency: string;
  lifecycle: string;
  mode: ForecastMode;
  horizon: number;
  startMonth: string;
  price: number;
  g2n: number;
  model: ModelId;
  series: Observation[];
  patient: PatientInputs;
  scenarios: ScenarioInputs;
  notes: string;
  evidence: Evidence[];
  versions: ReviewVersion[];
  sample: boolean;
}
export type ScenarioName = "Base" | "Upside" | "Downside";
export const MODEL_LABELS = {
  trend: "Linear trend",
  average: "Recent average",
  seasonal: "Seasonal naive",
};
const MAX_MONTHLY_VOLUME = 1e15;
export const SAMPLE_SERIES: Observation[] = Array.from({ length: 24 }, (_, i) => ({
  date: addMonths("2024-10", i),
  value: Math.round(
    9800 + i * 215 + [0, 320, 900, -400, -750, 140, 410, 630, 200, -250, 780, 1350][i % 12],
  ),
}));

export function addMonths(date: string, offset: number): string {
  const [year, month] = date.split("-").map(Number);
  const total = year * 12 + month - 1 + offset;
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
}
export function validMonth(value: unknown): value is string {
  return typeof value === "string" && /^(19\d{2}|20\d{2}|21\d{2})-(0[1-9]|1[0-2])$/.test(value);
}
export function createProject(sample = false): ForecastProject {
  return {
    id: crypto.randomUUID(),
    name: sample ? "Specialty brand · commercial plan" : "Untitled forecast",
    brand: sample ? "Demo Brand A" : "",
    therapy: "Oncology",
    country: "United States",
    owner: "",
    currency: "USD",
    lifecycle: "Established brand",
    mode: "historical",
    horizon: 12,
    startMonth: "2026-10",
    price: 25,
    g2n: 25,
    model: "auto",
    series: sample ? SAMPLE_SERIES.map((row) => ({ ...row })) : [],
    patient: {
      existingPatients: 12500,
      annualIncidence: 1800,
      diagnosis: 70,
      eligibility: 55,
      initiation: 8,
      capture: 22,
      discontinuation: 4,
      rampMonths: 6,
      unitsPerPatient: 30,
    },
    scenarios: {
      upsideVolume: 15,
      downsideVolume: -15,
      upsidePrice: 5,
      downsidePrice: -5,
      eventMonth: 6,
      eventImpact: 0,
      eventName: "",
    },
    notes: "",
    evidence: [],
    versions: [],
    sample,
  };
}

function csvCells(line: string): string[] {
  const cells: string[] = [];
  let cell = "",
    quoted = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (char === "," && !quoted) {
      cells.push(cell.trim());
      cell = "";
    } else cell += char;
  }
  if (quoted) throw new Error("Unclosed quotation mark in CSV. Use one record per line.");
  cells.push(cell.trim());
  return cells;
}

export function parseMonthlyCSV(text: string): Observation[] {
  const lines = text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => line.trim());
  if (lines.length < 13)
    throw new Error("Upload at least 12 monthly observations, plus a date,value header.");
  if (lines.length > 601) throw new Error("Upload at most 600 monthly observations.");
  const header = csvCells(lines[0]).map((cell) => cell.toLowerCase());
  const dateIndex = header.indexOf("date"),
    valueIndex = header.indexOf("value");
  if (dateIndex < 0 || valueIndex < 0)
    throw new Error("CSV must contain columns named date and value.");
  const rows = lines
    .slice(1)
    .map((line, index) => {
      const cells = csvCells(line);
      const rawDate = cells[dateIndex] || "";
      const date = rawDate.slice(0, 7);
      if (!validMonth(date) || !/^\d{4}-\d{2}(?:-01)?$/.test(rawDate)) {
        throw new Error(`Row ${index + 2}: use YYYY-MM or YYYY-MM-01 for monthly dates.`);
      }
      const rawValue = cells[valueIndex] || "";
      if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(rawValue))
        throw new Error(
          `Row ${index + 2}: volume must be a nonnegative number without currency symbols.`,
        );
      const value = Number(rawValue);
      if (!Number.isFinite(value) || value > MAX_MONTHLY_VOLUME)
        throw new Error(
          `Row ${index + 2}: volume exceeds the supported maximum of ${MAX_MONTHLY_VOLUME}.`,
        );
      return { date, value };
    })
    .sort((a, b) => a.date.localeCompare(b.date));
  for (let i = 1; i < rows.length; i++) {
    if (rows[i].date === rows[i - 1].date)
      throw new Error(`Duplicate month: ${rows[i].date}. Aggregate each month before upload.`);
    if (rows[i].date !== addMonths(rows[i - 1].date, 1))
      throw new Error(
        `Missing month after ${rows[i - 1].date}. Include every month; do not silently treat missing data as zero.`,
      );
  }
  return rows;
}

export function predict(
  values: number[],
  horizon: number,
  model: Exclude<ModelId, "auto">,
): number[] {
  if (!values.length) return [];
  const n = values.length;
  if (model === "seasonal" && n < 12)
    throw new Error("Seasonal forecasting requires at least 12 training months.");
  const mean = values.reduce((sum, value) => sum + value, 0) / n;
  const xMean = (n - 1) / 2;
  let numerator = 0,
    denominator = 0;
  values.forEach((value, i) => {
    numerator += (i - xMean) * (value - mean);
    denominator += (i - xMean) ** 2;
  });
  const slope = denominator ? numerator / denominator : 0;
  const recent = values.slice(-3);
  const average = recent.reduce((sum, value) => sum + value, 0) / recent.length;
  return Array.from({ length: horizon }, (_, i) =>
    Math.max(
      0,
      model === "trend"
        ? mean + slope * (n + i - xMean)
        : model === "average"
          ? average
          : values[n - 12 + (i % 12)],
    ),
  );
}

export function compareModels(series: Observation[]): { scores: ModelScore[]; holdout: number } {
  if (series.length < 12) return { scores: [], holdout: 0 };
  const holdout = Math.min(6, Math.max(3, Math.floor(series.length * 0.2)));
  const training = series.slice(0, -holdout).map((row) => row.value);
  const actual = series.slice(-holdout).map((row) => row.value);
  const models: Exclude<ModelId, "auto">[] =
    training.length >= 12 ? ["trend", "average", "seasonal"] : ["trend", "average"];
  const scores = models
    .map((id) => {
      const forecast = predict(training, holdout, id);
      const errors = actual.map((value, i) => Math.abs(value - forecast[i]));
      const totalActual = actual.reduce((sum, value) => sum + Math.abs(value), 0);
      return {
        id,
        label: MODEL_LABELS[id],
        mae: errors.reduce((sum, value) => sum + value, 0) / holdout,
        rmse: Math.sqrt(errors.reduce((sum, value) => sum + value ** 2, 0) / holdout),
        wape: totalActual
          ? (errors.reduce((sum, value) => sum + value, 0) / totalActual) * 100
          : null,
      };
    })
    .sort((a, b) => a.mae - b.mae);
  return { scores, holdout };
}

function clampRate(value: number) {
  return Math.max(0, Math.min(1, value));
}
export function forecastProject(project: ForecastProject): {
  rows: Record<ScenarioName, ForecastRow[]>;
  selectedModel: string;
  scores: ModelScore[];
  holdout: number;
} {
  const { scores, holdout } = compareModels(project.series);
  const model = project.model === "auto" ? scores[0]?.id || "average" : project.model;
  const rows = { Base: [], Upside: [], Downside: [] } as Record<ScenarioName, ForecastRow[]>;
  const volumes =
    project.mode === "historical"
      ? predict(
          project.series.map((row) => row.value),
          project.horizon,
          model,
        )
      : [];
  const start =
    project.mode === "historical" && project.series.length
      ? addMonths(project.series[project.series.length - 1].date, 1)
      : project.startMonth;
  for (const scenario of ["Base", "Upside", "Downside"] as ScenarioName[]) {
    const volumeShift =
      scenario === "Upside"
        ? project.scenarios.upsideVolume
        : scenario === "Downside"
          ? project.scenarios.downsideVolume
          : 0;
    const priceShift =
      scenario === "Upside"
        ? project.scenarios.upsidePrice
        : scenario === "Downside"
          ? project.scenarios.downsidePrice
          : 0;
    const unitPrice = project.price * Math.max(0, 1 + priceShift / 100);
    const p = project.patient;
    let pool = (((p.existingPatients * p.diagnosis) / 100) * p.eligibility) / 100;
    let active = 0;
    for (let i = 0; i < project.horizon; i++) {
      const event =
        i + 1 >= project.scenarios.eventMonth
          ? Math.max(0, 1 + project.scenarios.eventImpact / 100)
          : 1;
      let volume: number,
        patients: number | null = null,
        starts: number | null = null;
      if (project.mode === "patient") {
        pool += ((((p.annualIncidence / 12) * p.diagnosis) / 100) * p.eligibility) / 100;
        const initiators = (pool * p.initiation) / 100;
        pool -= initiators;
        const ramp = Math.min(1, (i + 1) / Math.max(1, p.rampMonths));
        const capture = clampRate((p.capture / 100) * (1 + volumeShift / 100) * event * ramp);
        starts = initiators * capture;
        active = active * (1 - p.discontinuation / 100) + starts;
        patients = active;
        volume = active * p.unitsPerPatient;
      } else {
        if (!volumes.length) break;
        volume = volumes[i] * Math.max(0, 1 + volumeShift / 100) * event;
      }
      const grossSales = volume * unitPrice;
      rows[scenario].push({
        date: addMonths(start, i),
        volume,
        patients,
        starts,
        grossSales,
        netSales: grossSales * (1 - project.g2n / 100),
      });
    }
  }
  return {
    rows,
    selectedModel: project.mode === "patient" ? "Patient-flow baseline" : MODEL_LABELS[model],
    scores,
    holdout,
  };
}

export function isProject(value: unknown): value is ForecastProject {
  if (!value || typeof value !== "object") return false;
  const p = value as ForecastProject;
  const finite = (number: unknown, low: number, high: number) =>
    typeof number === "number" && Number.isFinite(number) && number >= low && number <= high;
  if (
    ![p.id, p.name, p.brand, p.therapy, p.country, p.owner, p.currency, p.lifecycle, p.notes].every(
      (v) => typeof v === "string",
    )
  )
    return false;
  if (
    !["USD", "EUR", "GBP", "INR"].includes(p.currency) ||
    !["historical", "patient"].includes(p.mode) ||
    !["auto", "trend", "average", "seasonal"].includes(p.model)
  )
    return false;
  if (
    !validMonth(p.startMonth) ||
    !finite(p.horizon, 1, 60) ||
    !Number.isInteger(p.horizon) ||
    !finite(p.price, 0, 1e9) ||
    !finite(p.g2n, 0, 100)
  )
    return false;
  if (
    !Array.isArray(p.series) ||
    p.series.length > 600 ||
    !p.series.every(
      (row) => row && validMonth(row.date) && finite(row.value, 0, MAX_MONTHLY_VOLUME),
    )
  )
    return false;
  if (p.series.some((row, i) => i > 0 && row.date !== addMonths(p.series[i - 1].date, 1)))
    return false;
  if (
    (p.series.length > 0 && p.series.length < 12) ||
    (p.model === "seasonal" && p.series.length < 12)
  )
    return false;
  if (!p.patient || !p.scenarios) return false;
  for (const key of [
    "diagnosis",
    "eligibility",
    "initiation",
    "capture",
    "discontinuation",
  ] as const)
    if (!finite(p.patient[key], 0, 100)) return false;
  for (const key of ["existingPatients", "annualIncidence", "unitsPerPatient"] as const)
    if (!finite(p.patient[key], 0, 1e12)) return false;
  if (!finite(p.patient.rampMonths, 1, 60)) return false;
  for (const key of [
    "upsideVolume",
    "downsideVolume",
    "upsidePrice",
    "downsidePrice",
    "eventImpact",
  ] as const)
    if (!finite(p.scenarios[key], -100, 100)) return false;
  if (!finite(p.scenarios.eventMonth, 1, 60) || typeof p.scenarios.eventName !== "string")
    return false;
  if (
    !Array.isArray(p.evidence) ||
    !p.evidence.every(
      (e) =>
        e && [e.id, e.title, e.url, e.rationale, e.addedAt].every((v) => typeof v === "string"),
    )
  )
    return false;
  if (typeof p.sample !== "boolean" || !Array.isArray(p.versions) || p.versions.length > 20)
    return false;
  return p.versions.every((version) => {
    if (
      !version ||
      ![version.id, version.savedAt, version.name].every((v) => typeof v === "string") ||
      !version.inputs ||
      !version.rows
    )
      return false;
    if (!isProject({ ...version.inputs, versions: [] })) return false;
    return (["Base", "Upside", "Downside"] as const).every((name) => {
      const rows = version.rows[name];
      return (
        Array.isArray(rows) &&
        rows.length === version.inputs.horizon &&
        rows.every(
          (row) =>
            row &&
            validMonth(row.date) &&
            [row.volume, row.grossSales, row.netSales].every((v) => finite(v, 0, 1e40)) &&
            [row.patients, row.starts].every((v) => v === null || finite(v, 0, 1e40)),
        )
      );
    });
  });
}

export function safeURL(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function exportCSV(rows: Record<ScenarioName, ForecastRow[]>): string {
  return (
    "date,scenario,volume,active_brand_patients,new_brand_starts,gross_sales,net_sales\n" +
    (Object.entries(rows) as [ScenarioName, ForecastRow[]][])
      .flatMap(([name, data]) =>
        data.map((row) =>
          [
            row.date,
            name,
            row.volume.toFixed(2),
            row.patients?.toFixed(2) || "",
            row.starts?.toFixed(2) || "",
            row.grossSales.toFixed(2),
            row.netSales.toFixed(2),
          ].join(","),
        ),
      )
      .join("\n")
  );
}
