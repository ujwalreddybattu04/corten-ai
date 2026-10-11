import { api, ApiRequestError } from "@/lib/api";

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
  checks: {
    column: number;
    year: number;
    target: number;
    actual: number;
    absolute_error: number;
    passed: boolean;
  }[];
  series: {
    name: string;
    unit: string;
    input_min: number;
    input_max: number;
    monthly_min: number;
    monthly_max: number;
    first_month: number;
    outside_range_months: number;
  }[];
};

function upload(
  file: File,
  action: string,
  encoding: CsvEncoding,
  mode?: InterpolationMode,
  signal?: AbortSignal,
  format?: string,
  calculationId?: string,
) {
  const body = new FormData();
  body.append("file", file);
  const query = new URLSearchParams({ encoding });
  if (mode) query.set("mode", mode);
  if (format) query.set("format", format);
  if (calculationId) query.set("calculation_id", calculationId);
  return api.upload(`/api/v1/interpolation/${action}?${query}`, body, { signal });
}

function retryDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const canceled = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", canceled);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", canceled, { once: true });
  });
}

async function preview(
  file: File,
  encoding: CsvEncoding,
  signal: AbortSignal,
): Promise<InputPreview> {
  for (let attempt = 0; ; attempt++) {
    signal.throwIfAborted();
    try {
      return await (await upload(file, "preview", encoding, undefined, signal)).json();
    } catch (failure) {
      signal.throwIfAborted();
      const temporary =
        failure instanceof ApiRequestError && [502, 503, 504].includes(failure.status);
      if (!temporary) throw failure;
      if (attempt >= 2)
        throw new ApiRequestError(
          "The calculation service is temporarily unavailable. Your file is still selected; please try again in a moment.",
          failure.status,
        );
      // Validation is stateless. Retry only transient service errors, keeping
      // the same file and encoding; replacements/unmounts cancel the delay.
      await retryDelay(2000 * (attempt + 1), signal);
    }
  }
}

export const interpolationService = {
  preview,
  calculate: async (
    file: File,
    encoding: CsvEncoding,
    mode: InterpolationMode,
    signal: AbortSignal,
  ): Promise<InterpolationResult> =>
    (await upload(file, "calculate", encoding, mode, signal)).json(),
  export: async (
    file: File,
    encoding: CsvEncoding,
    result: InterpolationResult,
    format: "csv" | "json" | "pdf",
    signal: AbortSignal,
  ): Promise<Blob> =>
    (
      await upload(file, "export", encoding, result.mode, signal, format, result.calculation_id)
    ).blob(),
};
