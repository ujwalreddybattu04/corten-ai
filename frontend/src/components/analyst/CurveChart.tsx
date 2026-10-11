"use client";

import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from "react";
import { chartScale, displayValue } from "@/lib/interpolationDisplay";
import type { InterpolationResult } from "@/services/interpolationService";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Animations reveal verified geometry; they never change the underlying values. */
export default function CurveChart({
  result,
  column,
}: {
  result: InterpolationResult;
  column: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [keyboard, setKeyboard] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(960);
  const description = useId();
  const gradient = useId();
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(240, Math.round(entries[0].contentRect.width))),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const { values, yearly, scale } = useMemo(() => {
    const values = result.monthly.map((row) => row.values[column]);
    const yearly = result.yearly.map((row) => row.values[column]);
    return { values, yearly, scale: chartScale([...values, ...yearly]) };
  }, [result, column]);
  const height = width < 500 ? 270 : 340,
    left = width < 500 ? 64 : 76,
    right = width - 20,
    top = 30,
    bottom = height - 50;
  const x = (index: number) => left + (index / Math.max(1, values.length - 1)) * (right - left);
  const y = (value: number) => bottom - scale.fraction(value) * (bottom - top);
  const path = values
    .map((value, index) => `${index ? "L" : "M"}${x(index)},${y(value)}`)
    .join(" ");
  const area = `${path} L${x(values.length - 1)},${bottom} L${x(0)},${bottom} Z`;
  const selected = hover === null ? null : result.monthly[hover];
  const target = selected ? result.yearly[Math.floor(hover! / 12)].values[column] : null;
  const labelWidth = Math.max(
    70,
    Math.max(...result.yearly.map((row) => String(row.year).length)) * 7,
  );
  const stride = Math.max(
    1,
    Math.ceil(yearly.length / Math.max(2, Math.floor((right - left) / labelWidth))),
  );
  const inspect = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const position = ((event.clientX - rect.left) / rect.width) * width;
    setKeyboard(false);
    setHover(
      Math.max(
        0,
        Math.min(
          values.length - 1,
          Math.round(((position - left) / (right - left)) * (values.length - 1)),
        ),
      ),
    );
  };
  return (
    <div className="aw-curve" ref={container}>
      <div className="aw-curve-legend">
        <span>
          <i className="aw-line-key" />
          Monthly series
        </span>
        <span>
          <i className="aw-target-key" />
          {result.mode === "average" ? "Yearly average target" : "December target"}
        </span>
      </div>
      <div className="aw-plot">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          tabIndex={0}
          aria-label={`${result.columns[column]} monthly curve and yearly ${result.mode === "average" ? "average" : "December"} targets`}
          aria-describedby={description}
          onFocus={(event) => {
            if (event.currentTarget.matches(":focus-visible")) {
              setKeyboard(true);
              setHover((current) => current ?? 0);
            }
          }}
          onBlur={() => {
            setKeyboard(false);
            setHover(null);
          }}
          onKeyDown={(event) => {
            if (["ArrowRight", "ArrowLeft", "Home", "End", "Escape"].includes(event.key)) {
              event.preventDefault();
              setKeyboard(true);
              if (event.key === "Escape") setHover(null);
              else if (event.key === "Home") setHover(0);
              else if (event.key === "End") setHover(values.length - 1);
              else
                setHover(
                  Math.max(
                    0,
                    Math.min(
                      values.length - 1,
                      (hover ?? 0) + (event.key === "ArrowRight" ? 1 : -1),
                    ),
                  ),
                );
            }
          }}
          onPointerMove={inspect}
          onPointerDown={inspect}
          onPointerLeave={(event) => {
            if (event.pointerType !== "touch") setHover(null);
          }}
        >
          <title>
            {result.columns[column]} · {result.mode} interpolation
          </title>
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity=".11" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          </defs>
          {Array.from({ length: 5 }, (_, index) => {
            const position = bottom - (index / 4) * (bottom - top);
            const tick =
              (scale.lower + (index / 4) * (scale.upper - scale.lower)) * scale.magnitude;
            return (
              <g key={index}>
                <line className="aw-curve-grid" x1={left} x2={right} y1={position} y2={position} />
                <text x={left - 12} y={position + 4} textAnchor="end">
                  {Math.abs(tick) >= 1e6 || (tick !== 0 && Math.abs(tick) < 0.01)
                    ? tick.toExponential(1)
                    : Number(tick.toPrecision(4))}
                  {result.units[column]}
                </text>
              </g>
            );
          })}
          <path className="aw-curve-area" d={area} fill={`url(#${gradient})`} />
          <path className="aw-curve-path" d={path} fill="none" pathLength={1} />
          {yearly.map((value, index) => (
            <g key={index}>
              <circle
                className="aw-curve-target"
                cx={x(index * 12 + (result.mode === "exit" ? 11 : 5.5))}
                cy={y(value)}
                r={3.5}
              />
              {(index % stride === 0 || index === yearly.length - 1) && (
                <text
                  x={
                    yearly.length === 1
                      ? (left + right) / 2
                      : index === 0
                        ? left
                        : index === yearly.length - 1
                          ? right
                          : x(index * 12 + 5.5)
                  }
                  y={bottom + 26}
                  textAnchor={
                    yearly.length === 1
                      ? "middle"
                      : index === 0
                        ? "start"
                        : index === yearly.length - 1
                          ? "end"
                          : "middle"
                  }
                >
                  {result.yearly[index].year}
                </text>
              )}
            </g>
          ))}
          <text x={(left + right) / 2} y={height - 7} textAnchor="middle">
            Year
          </text>
          {selected && hover !== null && (
            <g className="aw-curve-inspection">
              <line className="aw-curve-guide" x1={x(hover)} x2={x(hover)} y1={top} y2={bottom} />
              <circle
                className="aw-curve-point"
                cx={x(hover)}
                cy={y(selected.values[column])}
                r={4.5}
              />
            </g>
          )}
        </svg>
        {selected && hover !== null && (
          <div
            className="aw-chart-tooltip"
            aria-hidden="true"
            style={{
              left: `${(Math.max(0, Math.min(width - 200, x(hover) - 100)) / width) * 100}%`,
            }}
          >
            <span>
              {MONTHS[selected.month - 1]} · Year {selected.year}
            </span>
            <strong>{displayValue(selected.values[column], true, result.units[column])}</strong>
            <small>
              {result.mode === "average" ? "Yearly average" : "December target"}:{" "}
              {displayValue(target!, true, result.units[column])}
            </small>
          </div>
        )}
      </div>
      <div className="aw-chart-readout" aria-live={keyboard ? "polite" : "off"} aria-atomic="true">
        <span>
          {selected
            ? `${MONTHS[selected.month - 1]} · Year ${selected.year}`
            : "Inspect monthly values"}
        </span>
        <strong>
          {selected
            ? displayValue(selected.values[column], true, result.units[column])
            : "Hover, tap, or use the arrow keys"}
        </strong>
      </div>
      <p id={description} className="aw-curve-caption">
        {result.mode === "average"
          ? "Markers show yearly average targets. Each target is verified against all 12 months."
          : "Every December is fixed to its yearly input. The first year is included in the calculation."}{" "}
        Use Left/Right to inspect months, Home/End to jump, and Escape to clear.
      </p>
    </div>
  );
}
