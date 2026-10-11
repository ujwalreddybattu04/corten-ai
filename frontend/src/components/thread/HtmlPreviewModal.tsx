"use client";

import { useState, useEffect, useRef, useCallback, memo } from "react";
import { createPortal } from "react-dom";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

// ─── Types ────────────────────────────────────────────────────────────────────
interface ConsoleLine {
  level: "log" | "warn" | "error" | "info" | "debug";
  text: string;
}

type DeviceMode = "desktop" | "tablet" | "mobile";

interface HtmlPreviewModalProps {
  code: string;
  onClose: () => void;
}

// ─── Device config ────────────────────────────────────────────────────────────
const DEVICES = {
  desktop: { label: "Desktop", width: "100%"  },
  tablet:  { label: "Tablet",  width: "768px" },
  mobile:  { label: "Mobile",  width: "390px" },
} as const;

// ─── Console capture script injected into every preview ───────────────────────
// Intercepts console.log/warn/error and window.onerror → postMessage to parent
const INJECT = `<script>(function(){
  var _p=function(l,t){try{parent.postMessage({type:'console',level:l,text:t},'*');}catch(e){}};
  ['log','warn','error','info','debug'].forEach(function(m){
    var o=console[m];
    console[m]=function(){
      var t=Array.prototype.slice.call(arguments).map(function(a){
        try{return typeof a==='object'&&a!==null?JSON.stringify(a,null,2):String(a);}catch(e){return String(a);}
      }).join(' ');
      _p(m,t);
      try{o&&o.apply(console,arguments);}catch(e){}
    };
  });
  window.onerror=function(msg,src,line,col,err){
    _p('error',(err&&(err.stack||err.message)||msg)+(line?' (line '+line+')':''));
    return false;
  };
  window.addEventListener('unhandledrejection',function(e){
    try{_p('error','Unhandled: '+(e.reason&&(e.reason.stack||e.reason.message||String(e.reason))));}catch(x){}
  });
  parent.postMessage({type:'preview-loaded'},'*');
})()\x3c/script>`;

function buildSrcdoc(html: string): string {
  const t = html.trim();
  // Full HTML document
  if (/<html[\s>]/i.test(t)) {
    if (/<\/head>/i.test(t)) return t.replace(/<\/head>/i, INJECT + "</head>");
    if (/<body[\s>]/i.test(t)) return t.replace(/(<body(?:\s[^>]*)?>)/i, "$1" + INJECT);
    return INJECT + t;
  }
  // Fragment — wrap in minimal document
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>*{box-sizing:border-box}</style>${INJECT}</head><body style="margin:0">${t}</body></html>`;
}

// ─── SVG icons (inline — no extra dep) ───────────────────────────────────────
const IconDesktop = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>
  </svg>
);
const IconTablet = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect width="16" height="20" x="4" y="2" rx="2"/><line x1="12" x2="12.01" y1="18" y2="18"/>
  </svg>
);
const IconMobile = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect width="14" height="20" x="5" y="2" rx="2"/><line x1="12" x2="12.01" y1="18" y2="18"/>
  </svg>
);
const DEVICE_ICONS = { desktop: <IconDesktop />, tablet: <IconTablet />, mobile: <IconMobile /> };

// ─── Component ────────────────────────────────────────────────────────────────
const HtmlPreviewModal = memo(function HtmlPreviewModal({ code, onClose }: HtmlPreviewModalProps) {
  const [mounted,       setMounted]       = useState(false);
  const [showCode,      setShowCode]      = useState(true);
  const [device,        setDevice]        = useState<DeviceMode>("desktop");
  const [consoleLines,  setConsoleLines]  = useState<ConsoleLine[]>([]);
  const [consoleOpen,   setConsoleOpen]   = useState(false);
  const [loading,       setLoading]       = useState(true);
  const [refreshKey,    setRefreshKey]    = useState(0);
  const [srcdoc,        setSrcdoc]        = useState("");

  const consoleEndRef = useRef<HTMLDivElement>(null);

  // SSR guard
  useEffect(() => { setMounted(true); return () => setMounted(false); }, []);

  // Build srcdoc
  useEffect(() => {
    setSrcdoc(buildSrcdoc(code));
    setLoading(true);
    setConsoleLines([]);
  }, [code, refreshKey]);

  // ESC to close
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  // Receive messages from sandboxed iframe
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      const d = e.data;
      if (!d || typeof d !== "object") return;
      if (d.type === "preview-loaded") { setLoading(false); return; }
      if (d.type === "console") {
        const line = { level: d.level as ConsoleLine["level"], text: d.text };
        setConsoleLines((p) => [...p, line]);
        if (d.level === "error" || d.level === "warn") setConsoleOpen(true);
        requestAnimationFrame(() => consoleEndRef.current?.scrollIntoView({ behavior: "smooth" }));
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const openInNewTab = useCallback(() => {
    const blob = new Blob([buildSrcdoc(code)], { type: "text/html" });
    const url  = URL.createObjectURL(blob);
    const w    = window.open(url, "_blank");
    if (w) setTimeout(() => URL.revokeObjectURL(url), 8000);
  }, [code]);

  if (!mounted) return null;

  const errorCount = consoleLines.filter((l) => l.level === "error").length;
  const warnCount  = consoleLines.filter((l) => l.level === "warn").length;
  const badgeClass = errorCount > 0 ? " error" : warnCount > 0 ? " warn" : "";

  // ── Iframe element (shared between desktop + framed modes) ──────────────────
  const iframeEl = srcdoc ? (
    <iframe
      key={refreshKey}
      srcDoc={srcdoc}
      sandbox="allow-scripts allow-popups allow-forms allow-modals"
      title="HTML Preview"
      className="hp-iframe"
      onLoad={() => setLoading(false)}
    />
  ) : null;

  const modal = (
    <div className="hp-overlay" role="dialog" aria-modal="true" aria-label="HTML Preview">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="hp-header">
        {/* Left: hide code + device picker */}
        <div className="hp-header-left">
          <button className="hp-hide-code-btn" onClick={() => setShowCode((v) => !v)}>
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ transform: showCode ? "rotate(0deg)" : "rotate(180deg)", transition: "transform 0.2s" }}>
              <polyline points="15 18 9 12 15 6" />
            </svg>
            {showCode ? "Hide code" : "Show code"}
          </button>

          <div className="hp-header-divider" />

          <div className="hp-device-toggle">
            {(["desktop", "tablet", "mobile"] as DeviceMode[]).map((d) => (
              <button
                key={d}
                className={`hp-device-btn${device === d ? " active" : ""}`}
                onClick={() => setDevice(d)}
                title={DEVICES[d].label}
              >
                {DEVICE_ICONS[d]}
              </button>
            ))}
          </div>
        </div>

        {/* Center: fake browser URL bar */}
        <div className="hp-header-center">
          <div className="hp-url-bar">
            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24"
              fill="none" stroke="#4ade80" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ flexShrink: 0 }}>
              <rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <span className="hp-url-text">preview — {DEVICES[device].label}</span>
          </div>
        </div>

        {/* Right: refresh, new tab, close */}
        <div className="hp-header-right">
          <button className="hp-icon-btn" onClick={refresh} title="Refresh">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
              <path d="M21 3v5h-5"/>
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
            </svg>
          </button>

          <button className="hp-icon-btn" onClick={openInNewTab} title="Open in new tab">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 3h6v6"/><path d="M10 14 21 3"/>
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            </svg>
          </button>

          <div className="hp-header-divider" />

          <button className="hp-icon-btn hp-close-btn" onClick={onClose} title="Close (Esc)">
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className={`hp-body${!showCode ? " hp-body-preview-only" : ""}`}>

        {/* Code panel */}
        {showCode && (
          <div className="hp-code-panel">
            <div className="hp-code-lang-badge">html</div>
            <SyntaxHighlighter
              language="html"
              style={oneDark}
              customStyle={{
                margin: 0, padding: "20px", background: "transparent",
                fontSize: "13px", lineHeight: "1.65",
                flex: 1, overflow: "auto", borderRadius: 0,
              }}
              showLineNumbers
              lineNumberStyle={{ color: "rgba(255,255,255,0.18)", minWidth: "2.8em", paddingRight: "16px" }}
              wrapLongLines={false}
              PreTag="div"
            >
              {code}
            </SyntaxHighlighter>
          </div>
        )}

        {/* Preview panel */}
        <div className="hp-preview-panel">

          {/* Preview viewport */}
          <div className={`hp-preview-area hp-device-${device}`}>

            {device === "desktop" && (
              <div className="hp-desktop-frame">
                {loading && <div className="hp-shimmer" />}
                {iframeEl}
              </div>
            )}

            {device === "tablet" && (
              <div className="hp-device-frame hp-frame-tablet">
                <div className="hp-device-screen">
                  {loading && <div className="hp-shimmer" />}
                  {iframeEl}
                </div>
              </div>
            )}

            {device === "mobile" && (
              <div className="hp-device-frame hp-frame-mobile">
                <div className="hp-mobile-notch" />
                <div className="hp-device-screen">
                  {loading && <div className="hp-shimmer" />}
                  {iframeEl}
                </div>
                <div className="hp-mobile-home" />
              </div>
            )}
          </div>

          {/* Console drawer */}
          <div className={`hp-console${consoleOpen ? " hp-console-open" : ""}`}>
            <button className="hp-console-bar" onClick={() => setConsoleOpen((v) => !v)}>
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                style={{ transform: consoleOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s", flexShrink: 0 }}>
                <polyline points="18 15 12 9 6 15" />
              </svg>
              <span className="hp-console-label">Console</span>
              {consoleLines.length > 0 && (
                <span className={`hp-console-count${badgeClass}`}>{consoleLines.length}</span>
              )}
              {consoleLines.length > 0 && (
                <button
                  className="hp-console-clear"
                  onClick={(e) => { e.stopPropagation(); setConsoleLines([]); }}
                >
                  Clear
                </button>
              )}
            </button>

            {consoleOpen && (
              <div className="hp-console-body">
                {consoleLines.length === 0 ? (
                  <div className="hp-console-empty">No console output</div>
                ) : (
                  consoleLines.map((line, i) => (
                    <div key={i} className={`hp-cline hp-cline-${line.level}`}>
                      <span className="hp-cline-icon">
                        {line.level === "error" ? "✕" : line.level === "warn" ? "⚠" : line.level === "info" ? "ℹ" : ">"}
                      </span>
                      <span className="hp-cline-text">{line.text}</span>
                    </div>
                  ))
                )}
                <div ref={consoleEndRef} />
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
});

export default HtmlPreviewModal;
