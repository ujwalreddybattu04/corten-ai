import { NextRequest, NextResponse } from "next/server";

// ─── Wandbox compiler map (free, no API key) ──────────────────────────────────
// POST https://wandbox.org/api/compile.json
// { code, compiler, options?, stdin? }
// Response: { status, program_output, program_error, compiler_output, compiler_error }
const WANDBOX_MAP: Record<string, { compiler: string; options?: string }> = {
  c:       { compiler: "gcc-head",          options: "-Wall -O2" },
  java:    { compiler: "openjdk-head" },
  cpp:     { compiler: "gcc-head",          options: "-std=c++17 -Wall -O2" },
  "c++":   { compiler: "gcc-head",          options: "-std=c++17 -Wall -O2" },
  rust:    { compiler: "rust-head" },
  go:      { compiler: "go-head" },
  ruby:    { compiler: "ruby-head" },
  rb:      { compiler: "ruby-head" },
  php:     { compiler: "php-head" },
  lua:     { compiler: "luajit-head" },
  csharp:  { compiler: "mono-head" },
  cs:      { compiler: "mono-head" },
  swift:   { compiler: "swift-head" },
  kotlin:  { compiler: "kotlin-head" },
  bash:    { compiler: "bash" },
  sh:      { compiler: "bash" },
};

// Simple in-memory rate limiter (per IP, 15 exec/min)
const execLog = new Map<string, number[]>();
const RATE_WINDOW = 60_000;
const RATE_LIMIT = 15;

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const times = (execLog.get(ip) ?? []).filter((t) => now - t < RATE_WINDOW);
  if (times.length >= RATE_LIMIT) return true;
  execLog.set(ip, [...times, now]);
  return false;
}

export async function POST(req: NextRequest) {
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    req.headers.get("x-real-ip") ??
    "unknown";

  if (isRateLimited(ip)) {
    return NextResponse.json(
      { error: "Rate limit exceeded. Please wait a moment." },
      { status: 429 }
    );
  }

  let body: { language?: string; code?: string; stdin?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { language, code, stdin = "" } = body;

  if (!language || !code) {
    return NextResponse.json({ error: "Missing language or code" }, { status: 400 });
  }
  if (typeof code !== "string" || code.length > 100_000) {
    return NextResponse.json({ error: "Code too long (max 100KB)" }, { status: 400 });
  }

  const lang = language.toLowerCase();
  const meta = WANDBOX_MAP[lang];

  if (!meta) {
    return NextResponse.json(
      { error: `Language "${language}" is not supported for remote execution.` },
      { status: 400 }
    );
  }

  try {
    const res = await fetch("https://wandbox.org/api/compile.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        compiler: meta.compiler,
        ...(meta.options ? { options: meta.options } : {}),
        ...(stdin ? { stdin } : {}),
      }),
      signal: AbortSignal.timeout(30_000),
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: `Execution server error: ${res.status} — ${text.slice(0, 200)}` },
        { status: 502 }
      );
    }

    const data = await res.json();

    // Wandbox response fields
    const stdout: string = data.program_output ?? "";
    const stderr: string = data.program_error ?? "";
    const compilerError: string = data.compiler_error ?? "";
    const exitCode: number = parseInt(data.status ?? "0", 10);

    // Compilation failure
    if (compilerError && exitCode !== 0) {
      return NextResponse.json({
        stdout,
        stderr,
        error: compilerError,
        exitCode,
      });
    }

    return NextResponse.json({
      stdout,
      stderr,
      error: exitCode !== 0 ? stderr || "Runtime error" : null,
      exitCode,
    });
  } catch (err: any) {
    if (err.name === "TimeoutError" || err.name === "AbortError") {
      return NextResponse.json(
        { error: "Execution server timed out. Try again." },
        { status: 504 }
      );
    }
    return NextResponse.json(
      { error: `Failed to reach execution server: ${err.message}` },
      { status: 502 }
    );
  }
}
