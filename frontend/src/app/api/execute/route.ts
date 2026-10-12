import { NextRequest, NextResponse } from "next/server";
import { readExecutionInput, selectCompiler, supportedLanguage } from "@/lib/codeExecution";

const execLog = new Map<string, number[]>();
const RATE_WINDOW = 60_000;
const RATE_LIMIT = 15;

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  if (execLog.size >= 1000) for (const [key, times] of execLog) if (!times.some(time => now - time < RATE_WINDOW)) execLog.delete(key);
  if (!execLog.has(ip) && execLog.size >= 10000) return true;
  const times = (execLog.get(ip) ?? []).filter((t) => now - t < RATE_WINDOW);
  if (times.length >= RATE_LIMIT) return true;
  execLog.set(ip, [...times, now]);
  return false;
}

export async function POST(req: NextRequest) {
  if (!req.headers.get("content-type")?.startsWith("application/json")) return NextResponse.json({ error: "JSON content type is required." }, { status: 415 });
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

  let body;
  try { body = await readExecutionInput(req); }
  catch (error) { return NextResponse.json({ error: error instanceof Error && !error.message.startsWith("Unexpected") ? error.message : "Invalid JSON body" }, { status: 400 }); }
  const { language: lang, code, stdin } = body;
  if (!supportedLanguage(lang)) return NextResponse.json({ error: "This language is not available for remote execution." }, { status: 400 });

  try {
    const compiler = await selectCompiler(lang);
    if (!compiler) return NextResponse.json({ error: "The provider does not currently offer this language." }, { status: 503 });
    const res = await fetch("https://wandbox.org/api/compile.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        compiler,
        ...(["c", "cpp", "c++"].includes(lang) ? { "compiler-option-raw": lang === "c" ? "-Wall -O2" : "-std=c++17 -Wall -O2" } : {}),
        ...(stdin ? { stdin } : {}),
      }),
      signal: AbortSignal.any([req.signal, AbortSignal.timeout(30_000)]),
    });

    if (!res.ok) {

      return NextResponse.json(
        { error: "The execution provider is temporarily unavailable. Please retry." },
        { status: 502 }
      );
    }

    const data = await res.json();
    if (!data || typeof data !== "object" || !/^-?\d+$/.test(String(data.status ?? "")) || ["program_output", "program_error", "compiler_error"].some(key => data[key] !== undefined && typeof data[key] !== "string")) return NextResponse.json({ error: "The execution provider returned an incomplete result." }, { status: 502 });


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
      { error: "The execution provider is temporarily unavailable. Please retry." },
      { status: 502 }
    );
  }
}
