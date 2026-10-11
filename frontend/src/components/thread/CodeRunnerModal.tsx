"use client";

import {
  useState,
  useEffect,
  useCallback,
  useRef,
  memo,
} from "react";
import { createPortal } from "react-dom";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { usePyodideWorker } from "@/hooks/usePyodideWorker";

// ─── Types ────────────────────────────────────────────────────────────────────
export interface OutputLine {
  type: "stdout" | "stderr" | "error" | "info" | "image";
  text: string;
}

interface CodeRunnerModalProps {
  code: string;
  language: string;
  onClose: () => void;
}

// ─── Language sets ────────────────────────────────────────────────────────────
const PYODIDE_LANGS = new Set(["python", "py"]);
const IFRAME_LANGS = new Set(["javascript", "js", "typescript", "ts"]);

export const RUNNABLE_LANGS = new Set([
  "python", "py",
  "javascript", "js",
  "typescript", "ts",
  "java", "c", "cpp", "c++",
  "rust", "go",
  "ruby", "rb",
  "bash", "sh",
  "php", "lua", "kotlin",
  "csharp", "cs", "swift",
]);

export function isRunnable(lang: string): boolean {
  return RUNNABLE_LANGS.has(lang.toLowerCase());
}

// ─── JS Sandbox (singleton iframe) ───────────────────────────────────────────
let _jsiframe: HTMLIFrameElement | null = null;
let _jsReady = false;
const _jsQueue: Array<() => void> = [];
const _jsPending = new Map<
  string,
  { resolve: () => void; reject: (e: Error) => void }
>();
const _jsListeners = new Set<(line: OutputLine) => void>();

function _handleJsMsg(event: MessageEvent) {
  const { type, id, data } = event.data ?? {};
  if (type === "js-ready") {
    _jsReady = true;
    _jsQueue.forEach((fn) => fn());
    _jsQueue.length = 0;
    return;
  }
  if (type === "stdout" || type === "stderr") {
    const line: OutputLine = { type, text: data };
    _jsListeners.forEach((fn) => fn(line));
    return;
  }
  if (type === "result" || type === "error") {
    const p = _jsPending.get(id);
    if (!p) return;
    _jsPending.delete(id);
    if (type === "result") p.resolve();
    else p.reject(new Error(data));
  }
}

function _ensureJsSandbox(): HTMLIFrameElement {
  if (_jsiframe && document.body.contains(_jsiframe)) return _jsiframe;

  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-scripts");
  iframe.style.cssText = "display:none;position:fixed;pointer-events:none;";

  const html = `<!DOCTYPE html><html><body><script>
var stdoutSent=0;
function fmt(a){return typeof a==="object"?JSON.stringify(a,null,2):String(a);}
console.log=function(){var t=[].map.call(arguments,fmt).join(" ");parent.postMessage({type:"stdout",data:t},"*");};
console.warn=console.log;
console.error=function(){var t=[].map.call(arguments,fmt).join(" ");parent.postMessage({type:"stderr",data:t},"*");};
window.onerror=function(m,s,l,c,e){parent.postMessage({type:"error",id:window.__cid,data:e?e.message:m},"*");return true;};
window.addEventListener("message",function(ev){
  var d=ev.data;window.__cid=d.id;
  try{
    var AF=Object.getPrototypeOf(async function(){}).constructor;
    var fn=new AF(d.code);
    fn().then(function(r){parent.postMessage({type:"result",id:d.id,data:r!=null?String(r):""},"*");})
       .catch(function(e){parent.postMessage({type:"error",id:d.id,data:e.message},"*");});
  }catch(e){parent.postMessage({type:"error",id:d.id,data:e.message},"*");}
});
parent.postMessage({type:"js-ready"},"*");
<\/script></body></html>`;

  iframe.src = "data:text/html," + encodeURIComponent(html);
  document.body.appendChild(iframe);

  if (!(window as any).__crJsListenerAdded) {
    window.addEventListener("message", _handleJsMsg);
    (window as any).__crJsListenerAdded = true;
  }

  _jsiframe = iframe;
  return iframe;
}

function runInJsSandbox(
  code: string,
  onLine: (l: OutputLine) => void,
  timeoutMs = 15_000
): Promise<void> {
  return new Promise<void>((resolve: () => void, reject: (e: Error) => void) => {
    const id = crypto.randomUUID();
    _jsListeners.add(onLine);

    const cleanup = () => _jsListeners.delete(onLine);

    const timer = setTimeout(() => {
      cleanup();
      _jsPending.delete(id);
      reject(new Error("Execution timed out after 15s"));
    }, timeoutMs);

    _jsPending.set(id, {
      resolve: () => {
        clearTimeout(timer);
        cleanup();
        resolve();
      },
      reject: (e) => {
        clearTimeout(timer);
        cleanup();
        reject(e);
      },
    });

    const run = () => {
      try {
        const f = _ensureJsSandbox();
        f.contentWindow?.postMessage({ id, code }, "*");
      } catch (e: any) {
        clearTimeout(timer);
        cleanup();
        _jsPending.delete(id);
        reject(new Error("Sandbox error: " + e.message));
      }
    };

    if (_jsReady) {
      run();
    } else {
      _ensureJsSandbox();
      _jsQueue.push(run);
    }
  });
}

// ─── Component ────────────────────────────────────────────────────────────────
const CodeRunnerModal = memo(function CodeRunnerModal({
  code,
  language,
  onClose,
}: CodeRunnerModalProps) {
  const lang = language.toLowerCase().replace("c++", "cpp");
  const isPython = PYODIDE_LANGS.has(lang);
  const isJs = IFRAME_LANGS.has(lang);

  const [output, setOutput] = useState<OutputLine[]>([]);
  const [status, setStatus] = useState<
    "idle" | "init" | "running" | "done" | "error" | "stopped"
  >("idle");
  const [elapsed, setElapsed] = useState(0);
  const [showCode, setShowCode] = useState(true);
  const [mounted, setMounted] = useState(false);

  const outputRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const startRef = useRef(0);
  const isRunningRef = useRef(false);

  const { runPython, stop: stopPython, isReady: pyReady } =
    usePyodideWorker();

  // SSR guard
  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  // ESC to close
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  // Cleanup timer
  useEffect(() => () => clearInterval(timerRef.current), []);

  const append = useCallback((line: OutputLine) => {
    setOutput((p) => [...p, line]);
    requestAnimationFrame(() => {
      if (outputRef.current) {
        outputRef.current.scrollTop = outputRef.current.scrollHeight;
      }
    });
  }, []);

  const startTimer = useCallback(() => {
    startRef.current = Date.now();
    clearInterval(timerRef.current);
    timerRef.current = setInterval(
      () => setElapsed(Date.now() - startRef.current),
      100
    );
  }, []);

  const stopTimer = useCallback(() => {
    clearInterval(timerRef.current);
    setElapsed(Date.now() - startRef.current);
  }, []);

  const run = useCallback(async () => {
    if (isRunningRef.current) return;
    isRunningRef.current = true;

    setOutput([]);
    setElapsed(0);
    startTimer();
    append({ type: "info", text: "Run started" });

    try {
      if (isPython) {
        if (!pyReady) {
          setStatus("init");
          append({ type: "info", text: "Initializing environment..." });

          // Wait for Pyodide to be ready (up to 60s)
          await new Promise<void>((resolve, reject) => {
            const check = setInterval(() => {
              if (pyReady) {
                clearInterval(check);
                resolve();
              }
            }, 300);
            setTimeout(() => {
              clearInterval(check);
              reject(new Error("Timed out waiting for Python environment"));
            }, 60_000);
          });
        }

        setStatus("running");
        const result = await runPython(
          code,
          30_000,
          (line) => append({ type: "stdout", text: line }),
          (line) => append({ type: "stderr", text: line }),
          (b64) => append({ type: "image", text: b64 })
        );

        stopTimer();

        if (result.interrupted) {
          append({ type: "info", text: "Execution stopped" });
          setStatus("stopped");
        } else if (result.error) {
          append({ type: "error", text: result.error });
          setStatus("error");
        } else {
          setStatus("done");
        }
      } else if (isJs) {
        setStatus("running");
        append({ type: "info", text: "Running in browser sandbox..." });

        try {
          await runInJsSandbox(code, (l) => append(l));
          stopTimer();
          setStatus("done");
        } catch (e: any) {
          stopTimer();
          append({ type: "error", text: e.message });
          setStatus("error");
        }
      } else {
        // Remote execution via Piston
        setStatus("running");
        append({ type: "info", text: `Sending ${language} code to execution server...` });

        try {
          const res = await fetch("/api/execute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ language: lang, code }),
          });

          const data = await res.json();
          stopTimer();

          if (!res.ok) {
            append({ type: "error", text: data.error ?? `Server error: ${res.status}` });
            setStatus("error");
          } else {
            if (data.stdout) {
              data.stdout
                .split("\n")
                .filter(Boolean)
                .forEach((l: string) => append({ type: "stdout", text: l }));
            }
            if (data.stderr) {
              data.stderr
                .split("\n")
                .filter(Boolean)
                .forEach((l: string) => append({ type: "stderr", text: l }));
            }
            if (data.error) {
              append({ type: "error", text: data.error });
              setStatus("error");
            } else {
              setStatus("done");
            }
          }
        } catch (e: any) {
          stopTimer();
          append({ type: "error", text: "Network error: " + e.message });
          setStatus("error");
        }
      }
    } catch (e: any) {
      stopTimer();
      append({ type: "error", text: e.message });
      setStatus("error");
    } finally {
      isRunningRef.current = false;
    }
  }, [code, lang, language, isPython, isJs, pyReady, runPython, append, startTimer, stopTimer]);

  const stop = useCallback(() => {
    if (isPython) {
      stopPython();
    }
    clearInterval(timerRef.current);
    setElapsed(Date.now() - startRef.current);
    append({ type: "info", text: "Stopped by user" });
    setStatus("stopped");
    isRunningRef.current = false;
  }, [isPython, stopPython, append]);

  // Auto-run on open
  useEffect(() => {
    if (mounted) {
      run();
    }
  }, [mounted]);

  const isActive = status === "running" || status === "init";

  // ── Syntax language mapping for display ──
  const syntaxLang =
    lang === "cpp" ? "cpp" :
    lang === "cs" || lang === "csharp" ? "csharp" :
    lang === "ts" || lang === "typescript" ? "typescript" :
    lang === "rb" || lang === "ruby" ? "ruby" :
    lang === "sh" || lang === "bash" ? "bash" :
    lang;

  if (!mounted) return null;

  const modal = (
    <div className="cr-overlay" role="dialog" aria-modal="true" aria-label="Code Runner">
      {/* Header */}
      <div className="cr-header">
        <div className="cr-header-left">
          <button
            className="cr-hide-code-btn"
            onClick={() => setShowCode((v) => !v)}
            aria-label={showCode ? "Hide code" : "Show code"}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ transform: showCode ? "rotate(0deg)" : "rotate(180deg)", transition: "transform 0.2s" }}
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
            {showCode ? "Hide code" : "Show code"}
          </button>
        </div>

        <div className="cr-header-right">
          <span className="cr-console-label">Console</span>

          {/* Clear output */}
          <button
            className="cr-icon-btn"
            onClick={() => { setOutput([]); setStatus("idle"); }}
            title="Clear output"
            disabled={isActive}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="m19 6-.867 12.142A2 2 0 0 1 16.138 20H7.862a2 2 0 0 1-1.995-1.858L5 6" />
              <path d="M10 11v6" />
              <path d="M14 11v6" />
              <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
            </svg>
          </button>

          {/* Run / Stop */}
          {isActive ? (
            <button className="cr-stop-btn" onClick={stop}>
              <span className="cr-stop-icon" />
              Stop
            </button>
          ) : (
            <button className="cr-run-btn" onClick={run}>
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              Run
            </button>
          )}

          <div className="cr-header-divider" />

          {/* Close */}
          <button
            className="cr-icon-btn cr-close-btn"
            onClick={onClose}
            title="Close (Esc)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Body */}
      <div className={`cr-body${!showCode ? " cr-body-console-only" : ""}`}>
        {/* Code panel */}
        {showCode && (
          <div className="cr-code-panel">
            <div className="cr-code-lang-badge">{language}</div>
            <SyntaxHighlighter
              language={syntaxLang || "text"}
              style={oneDark}
              customStyle={{
                margin: 0,
                padding: "20px",
                background: "transparent",
                fontSize: "13px",
                lineHeight: "1.65",
                flex: 1,
                overflow: "auto",
                borderRadius: 0,
              }}
              showLineNumbers
              lineNumberStyle={{
                color: "rgba(255,255,255,0.18)",
                minWidth: "2.8em",
                paddingRight: "16px",
              }}
              wrapLongLines={false}
              PreTag="div"
            >
              {code}
            </SyntaxHighlighter>
          </div>
        )}

        {/* Console panel */}
        <div className="cr-console-panel" ref={outputRef}>
          {output.length === 0 && !isActive && (
            <div className="cr-console-empty">No output yet</div>
          )}

          {output.map((line, i) =>
            line.type === "image" ? (
              <div key={i} className="cr-output-line cr-output-image">
                <img
                  src={`data:image/png;base64,${line.text}`}
                  alt="Plot output"
                  style={{
                    maxWidth: "100%",
                    borderRadius: "6px",
                    marginTop: "8px",
                    marginBottom: "4px",
                    display: "block",
                  }}
                />
              </div>
            ) : (
              <div key={i} className={`cr-output-line cr-output-${line.type}`}>
                <span
                  className={`cr-output-prefix ${
                    line.type === "info"
                      ? "cr-output-prefix-info"
                      : line.type === "stderr" || line.type === "error"
                      ? "cr-output-prefix-err"
                      : "cr-output-prefix-out"
                  }`}
                >
                  {line.type === "info" ? ">" : line.type === "stderr" || line.type === "error" ? "!" : " "}
                </span>
                <span className="cr-output-text">{line.text}</span>
              </div>
            )
          )}

          {isActive && (
            <div className="cr-output-line cr-output-info cr-output-running">
              <span className="cr-spinner" />
              <span className="cr-output-text" style={{ color: "rgba(255,255,255,0.35)", fontStyle: "italic" }}>
                {status === "init" ? "Initializing environment..." : "Running..."}
              </span>
            </div>
          )}

          {(status === "done" || status === "error" || status === "stopped") &&
            output.length > 0 && (
              <div className="cr-output-footer">
                {status === "done" && `Finished in ${(elapsed / 1000).toFixed(2)}s`}
                {status === "error" && `Failed after ${(elapsed / 1000).toFixed(2)}s`}
                {status === "stopped" && `Stopped after ${(elapsed / 1000).toFixed(2)}s`}
              </div>
            )}
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
});

export default CodeRunnerModal;
