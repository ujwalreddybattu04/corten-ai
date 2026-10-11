import { api } from "@/lib/api";

export type InterpolationMode = "average" | "exit";
export type CsvEncoding = "auto" | "utf-8-sig" | "utf-16" | "cp1252" | "gb18030";
export type YearlyRow = { year: number; values: number[] };
export type MonthlyRow = YearlyRow & { month: number };
export type InputPreview = {
  columns: string[];
  units: string[];
  yearly: YearlyRow[];
  input_digest: string;
  encoding: string;
  delimiter: string;
  sorted_input: boolean;
};
export type InterpolationResult = InputPreview & {
  mode: InterpolationMode;
  monthly: MonthlyRow[];
  calculation_id: string;
  notes: string[];
  engine: { id: string; display_decimals: number; dependencies: Record<string, string> };
  checks: { column: number; year: number; target: number; actual: number; absolute_error: number; passed: boolean }[];
  series: { name: string; unit: string; input_min: number; input_max: number; monthly_min: number; monthly_max: number; first_month: number; outside_range_months: number }[];
};

function upload(file: File, action: string, encoding: CsvEncoding, mode?: InterpolationMode,
                signal?: AbortSignal, format?: string, calculationId?: string) {
  const body = new FormData();
  body.append("file", file);
  const query = new URLSearchParams({ encoding });
  if (mode) query.set("mode", mode);
  if (format) query.set("format", format);
  if (calculationId) query.set("calculation_id", calculationId);
  return api.upload(`/api/v1/interpolation/${action}?${query}`, body, { signal });
}

export const interpolationService = {
  preview: async (file: File, encoding: CsvEncoding, signal: AbortSignal): Promise<InputPreview> =>
    (await upload(file, "preview", encoding, undefined, signal)).json(),
  calculate: async (file: File, encoding: CsvEncoding, mode: InterpolationMode, signal: AbortSignal): Promise<InterpolationResult> =>
    (await upload(file, "calculate", encoding, mode, signal)).json(),
  export: async (file: File, encoding: CsvEncoding, result: InterpolationResult, format: "csv" | "json" | "pdf", signal: AbortSignal): Promise<Blob> =>
    (await upload(file, "export", encoding, result.mode, signal, format, result.calculation_id)).blob(),
};
