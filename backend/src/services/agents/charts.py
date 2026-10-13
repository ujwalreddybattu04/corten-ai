"""Charts for Space agents: a React + Recharts artifact built from fetched data.

The model never retypes numbers: data tools register datasets, and the chart is generated here from those exact
values. The artifact runs in the existing sandboxed artifact runtime (React, Recharts).
"""
import json
import re
from dataclasses import dataclass, field

MAX_POINTS = 400
PALETTE = ["#2563eb", "#16a34a", "#ea580c", "#9333ea", "#0891b2", "#db2777"]


@dataclass
class Dataset:
    id: str
    label: str
    points: list[tuple[str, float]]
    unit: str = ""
    x_kind: str = "date"          # "date", "year" or "category"
    source: str = ""              # human-readable source line
    summary: dict = field(default_factory=dict)
    topic: str = ""               # what the values measure, e.g. "Real GDP growth (annual %)"


def _clean_title(text: str, limit: int = 110) -> str:
    """Safe inside the artifact header attribute: no quotes, braces or line breaks."""
    return re.sub(r'["{}\n\r]+', " ", text or "").strip()[:limit] or "Chart"


def _thin(points: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Keep long series readable and small: evenly sample, always keeping the first and last point."""
    if len(points) <= MAX_POINTS:
        return points
    step = len(points) / MAX_POINTS
    sampled = [points[int(i * step)] for i in range(MAX_POINTS - 1)]
    return sampled + [points[-1]]


def build_chart(datasets: list[Dataset], title: str, chart_type: str = "auto", rebase: bool = False,
                y_label: str = "") -> tuple[str, str]:
    """Return (artifact block, short description for the model)."""
    if not datasets:
        raise ValueError("No data to chart.")
    kinds = {dataset.x_kind for dataset in datasets}
    if len(kinds) > 1:
        raise ValueError("These datasets use different kinds of x values (dates, years, categories) and cannot share a chart.")
    x_kind = kinds.pop()
    auto_rebased = False
    if not rebase and len(datasets) > 1 and x_kind == "date":
        # Series in different currencies, or of very different size, are unreadable on one axis: compare growth instead.
        levels = [abs(sum(y for _, y in d.points) / len(d.points)) for d in datasets if d.points]
        if len({d.unit for d in datasets}) > 1 or (levels and min(levels) > 0 and max(levels) / min(levels) > 4):
            rebase = auto_rebased = True
    series, rows = [], {}
    for index, dataset in enumerate(datasets[:6]):
        points = _thin([(str(x), float(y)) for x, y in dataset.points if y is not None])
        if rebase and points and points[0][1]:
            base = points[0][1]
            points = [(x, round(y / base * 100, 3)) for x, y in points]
        key = f"s{index}"
        series.append({"key": key, "name": dataset.label[:80], "color": PALETTE[index % len(PALETTE)]})
        for x, y in points:
            rows.setdefault(x, {"x": x})[key] = y
    ordered = sorted(rows.values(), key=lambda row: row["x"]) if x_kind in ("date", "year") else list(rows.values())
    if chart_type not in ("line", "area", "bar"):
        chart_type = ("bar" if x_kind != "date" and len(ordered) <= 16 else
                      "area" if len(series) == 1 and x_kind == "date" else "line")
    unit = "index" if rebase else (datasets[0].unit if len({d.unit for d in datasets}) == 1 else "")
    stats = None
    if len(series) == 1 and not rebase and datasets[0].summary:
        s = datasets[0].summary
        stats = {"last": s.get("last"), "lastDate": s.get("end"), "change": s.get("change"), "changePct": s.get("change_pct"),
                 "high": s.get("high"), "highDate": s.get("high_date"), "low": s.get("low"), "lowDate": s.get("low_date")}
    sources = sorted({d.source for d in datasets if d.source})
    first, last = ordered[0]["x"], ordered[-1]["x"]
    subtitle = " · ".join(part for part in [
        f"{first} to {last}" if x_kind != "category" else "",
        ("Rebased to 100 at the start so different price levels compare fairly" if auto_rebased else "Rebased to 100 at the start")
        if rebase else (f"Values in {unit}" if unit and unit != "index" else ""),
        y_label,
    ] if part)
    spec = {"title": _clean_title(title, 140), "subtitle": subtitle, "kind": chart_type, "xKind": x_kind, "unit": unit,
            "series": series, "rows": ordered, "stats": stats, "source": "; ".join(sources)[:300]}
    code = REACT_CHART.replace("__SPEC__", json.dumps(spec, ensure_ascii=True, separators=(",", ":")))
    artifact = f':::artifact{{type="react" title="{_clean_title(title)}"}}\n{code}\n:::'
    changes = sorted(((d.summary["change_pct"], d.label) for d in datasets[:6]
                      if d.summary and d.summary.get("change_pct") is not None), reverse=True)
    description = (f"Chart '{spec['title']}' with {len(series)} series and {len(ordered)} points ({first} to {last}) is ready "
                   "and is shown to the user above your answer. Do not repeat its data or write chart code."
                   + (" The series were rebased to 100 at the start because their price levels differ." if auto_rebased else "")
                   + (" Change over each series' period, highest first: "
                      + " > ".join(f"{label} {pct:+.2f}%" for pct, label in changes) + "." if len(changes) > 1 else ""))
    return artifact, description


REACT_CHART = r'''import React from "react";
import { ResponsiveContainer, LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const SPEC = __SPEC__;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function compact(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const abs = Math.abs(value);
  if (abs >= 1e12) return (value / 1e12).toFixed(2) + "T";
  if (abs >= 1e9) return (value / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return (value / 1e6).toFixed(2) + "M";
  if (abs >= 1e4) return Math.round(value).toLocaleString("en-US");
  return value.toLocaleString("en-US", { maximumFractionDigits: abs < 10 ? 4 : 2 });
}

function withUnit(value) {
  const text = compact(value);
  if (!SPEC.unit || SPEC.unit === "index") return text;
  if (SPEC.unit === "%") return text + "%";
  if (SPEC.unit === "US$") return "$" + text;
  return text + " " + SPEC.unit;
}

function tickLabel(x) {
  if (SPEC.xKind !== "date" || typeof x !== "string" || x.length < 10) return x;
  const [year, month, day] = x.split("-");
  const spanYears = SPEC.rows.length > 1 ? Number(SPEC.rows[SPEC.rows.length - 1].x.slice(0, 4)) - Number(SPEC.rows[0].x.slice(0, 4)) : 0;
  return spanYears >= 2 ? MONTHS[Number(month) - 1] + " '" + year.slice(2) : MONTHS[Number(month) - 1] + " " + Number(day);
}

function Kpi({ label, value, detail, tone }) {
  return (
    <div style={{ minWidth: 92 }}>
      <div style={{ fontSize: 11, letterSpacing: "0.04em", textTransform: "uppercase", color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 650, marginTop: 3, color: tone || "#0f172a" }}>{value}</div>
      {detail ? <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 2 }}>{detail}</div> : null}
    </div>
  );
}

export default function Chart() {
  const { title, subtitle, kind, series, rows, stats, source } = SPEC;
  const up = stats && stats.change >= 0;
  const axis = { stroke: "#94a3b8", fontSize: 12, tickLine: false, axisLine: false };
  const tooltip = (
    <Tooltip
      formatter={(value, name) => [withUnit(value), name]}
      labelFormatter={(label) => label}
      contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", boxShadow: "0 8px 24px rgba(15,23,42,0.08)", fontSize: 13 }}
    />
  );
  const common = { data: rows, margin: { top: 8, right: 12, left: 0, bottom: 0 } };
  const grid = <CartesianGrid stroke="#eef2f7" vertical={false} />;
  const xAxis = <XAxis dataKey="x" tickFormatter={tickLabel} minTickGap={28} {...axis} />;
  const yAxis = <YAxis tickFormatter={compact} width={64} domain={["auto", "auto"]} {...axis} />;
  const legend = series.length > 1 ? <Legend wrapperStyle={{ fontSize: 13, paddingTop: 8 }} /> : null;
  let chart;
  if (kind === "bar") {
    chart = (
      <BarChart {...common}>{grid}{xAxis}{yAxis}{tooltip}{legend}
        {series.map((s) => <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} />)}
      </BarChart>
    );
  } else if (kind === "area") {
    chart = (
      <AreaChart {...common}>
        <defs>{series.map((s) => (
          <linearGradient key={s.key} id={"fill-" + s.key} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={s.color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={s.color} stopOpacity={0} />
          </linearGradient>))}
        </defs>
        {grid}{xAxis}{yAxis}{tooltip}{legend}
        {series.map((s) => <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} fill={"url(#fill-" + s.key + ")"} connectNulls />)}
      </AreaChart>
    );
  } else {
    chart = (
      <LineChart {...common}>{grid}{xAxis}{yAxis}{tooltip}{legend}
        {series.map((s) => <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={false} connectNulls />)}
      </LineChart>
    );
  }
  return (
    <div style={{ fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif", padding: "22px 24px 18px", color: "#0f172a", background: "#ffffff" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
        <div style={{ minWidth: 220, flex: "1 1 260px" }}>
          <div style={{ fontSize: 19, fontWeight: 650, letterSpacing: "-0.01em" }}>{title}</div>
          {subtitle ? <div style={{ fontSize: 13, color: "#64748b", marginTop: 5 }}>{subtitle}</div> : null}
        </div>
        {stats ? (
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
            <Kpi label="Latest" value={withUnit(stats.last)} detail={stats.lastDate} />
            <Kpi label="Change" value={(up ? "+" : "") + compact(stats.change) + (stats.changePct !== null ? " (" + (up ? "+" : "") + stats.changePct + "%)" : "")}
                 tone={up ? "#15803d" : "#b91c1c"} detail="over the period" />
            <Kpi label="High" value={withUnit(stats.high)} detail={stats.highDate} />
            <Kpi label="Low" value={withUnit(stats.low)} detail={stats.lowDate} />
          </div>
        ) : null}
      </div>
      <div style={{ height: 340, marginTop: 20 }}>
        <ResponsiveContainer width="100%" height="100%">{chart}</ResponsiveContainer>
      </div>
      {source ? <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 12 }}>Source: {source}</div> : null}
    </div>
  );
}
'''
