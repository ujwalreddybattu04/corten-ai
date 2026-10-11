export function displayValue(value: number, fullPrecision = false, unit = "") {
  if (fullPrecision) return String(value) + unit;
  if (value !== 0 && (Math.abs(value) >= 1e9 || Math.abs(value) < .005)) return value.toExponential(2) + unit;
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + unit;
}

/** Normalize before subtraction to avoid overflowing chart ranges. */
export function chartScale(values: number[]) {
  const magnitude = Math.max(...values.map(Math.abs)) || 1;
  const normalized = values.map(value => value / magnitude);
  const minimum = Math.min(...normalized), maximum = Math.max(...normalized);
  const padding = (maximum - minimum || Math.max(Math.abs(maximum), 1) * .1) * .12;
  const finiteLimit = Number.MAX_VALUE / magnitude;
  const lower = Math.max(-finiteLimit, minimum - padding), upper = Math.min(finiteLimit, maximum + padding);
  return { magnitude, lower, upper, fraction: (value: number) => (value / magnitude - lower) / (upper - lower) };
}

export function saveDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
