/**
 * Runs inside an artifact's sandboxed iframe (opaque origin, no access to the app, cookies or storage).
 * Compiles the model's React component with Sucrase and renders it. Only react, recharts and
 * lucide-react can be imported. Built into public/artifact-runtime by scripts/build-artifact-runtime.mjs.
 */
import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as Recharts from "recharts";
import * as Lucide from "lucide-react";
import { transform } from "sucrase";

const MODULES: Record<string, unknown> = {
    react: React, "react-dom": ReactDOM, "react-dom/client": ReactDOMClient, recharts: Recharts, "lucide-react": Lucide,
};

type Bridge = { require: (name: string) => unknown; module: { exports: Record<string, unknown> } };
declare global { interface Window { __cortenModule?: Bridge; __cortenReact?: typeof React } }

function notify(type: "ready" | "error", detail = "") {
    window.parent.postMessage({ source: "corten-artifact", type, detail: detail.slice(0, 2000) }, "*");
}

function showError(message: string) {
    const root = document.getElementById("root");
    if (root) {
        root.innerHTML = "";
        const box = document.createElement("div");
        box.setAttribute("role", "alert");
        box.style.cssText = "margin:24px;padding:16px 18px;border-radius:12px;background:#fef2f2;border:1px solid #fecaca;" +
            "color:#991b1b;font:14px/1.5 system-ui,sans-serif;white-space:pre-wrap";
        const title = document.createElement("strong");
        title.textContent = "This artifact could not run";
        const text = document.createElement("div");
        text.style.marginTop = "6px";
        text.textContent = message;  // textContent: never interpreted as HTML
        box.append(title, text);
        root.append(box);
    }
    notify("error", message);
}

class Boundary extends React.Component<{ children: React.ReactNode }, { error: string }> {
    state = { error: "" };
    static getDerivedStateFromError(error: unknown) { return { error: error instanceof Error ? error.message : String(error) }; }
    componentDidCatch(error: unknown) { notify("error", error instanceof Error ? error.message : String(error)); }
    render() {
        if (!this.state.error) return this.props.children;
        return React.createElement("div", { role: "alert", style: { margin: 24, padding: 16, borderRadius: 12, background: "#fef2f2",
            border: "1px solid #fecaca", color: "#991b1b", font: "14px/1.5 system-ui, sans-serif" } },
            React.createElement("strong", null, "This artifact stopped with an error"),
            React.createElement("div", { style: { marginTop: 6 } }, this.state.error));
    }
}

function run() {
    window.addEventListener("error", event => showError(event.message || "Unknown error"));
    window.addEventListener("unhandledrejection", event => showError(String(event.reason?.message ?? event.reason ?? "Unknown error")));
    const payload = document.getElementById("artifact-source")?.textContent ?? "";
    let source = "";
    try { source = JSON.parse(payload); } catch { return showError("The artifact content is missing."); }
    let compiled: string;
    try {
        compiled = transform(source, { transforms: ["jsx", "typescript", "imports"], production: true }).code;
    } catch (error) {
        return showError("Syntax error: " + (error instanceof Error ? error.message : String(error)));
    }
    const bridge: Bridge = {
        module: { exports: {} },
        require: (name: string) => {
            if (name in MODULES) return MODULES[name];
            throw new Error(`"${name}" is not available in artifacts. Only react, recharts and lucide-react can be imported.`);
        },
    };
    window.__cortenModule = bridge;
    window.__cortenReact = React;
    // An inline script (allowed by the page policy) instead of eval, which the policy forbids.
    const script = document.createElement("script");
    script.textContent = "(function(require,module,exports,React){\n" + compiled +
        "\n})(window.__cortenModule.require,window.__cortenModule.module,window.__cortenModule.module.exports,window.__cortenReact);";
    document.body.appendChild(script);
    const exported = bridge.module.exports;
    const Component = (exported.default ?? Object.values(exported).find(value => typeof value === "function")) as React.ComponentType | undefined;
    if (typeof Component !== "function") return showError("The artifact does not export a React component.");
    ReactDOMClient.createRoot(document.getElementById("root")!).render(
        React.createElement(Boundary, null, React.createElement(Component)));
    notify("ready");
}

run();
