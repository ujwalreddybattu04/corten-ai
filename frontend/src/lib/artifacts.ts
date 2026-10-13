/** Artifacts in answers: parsing ":::artifact{...}" blocks and building their sandbox documents. */

export type ArtifactType = "react" | "html" | "mermaid" | "svg" | "markdown" | "code";
const TYPES: ArtifactType[] = ["react", "html", "mermaid", "svg", "markdown", "code"];

export interface Artifact {
    kind: "artifact";
    key: string;
    type: ArtifactType;
    title: string;
    language: string;
    content: string;
    /** False while the answer is still streaming the artifact. */
    complete: boolean;
}
export type Segment = { kind: "text"; text: string } | Artifact;

const OPEN = /(^|\n)[ \t]*:::artifact\{([^}\n]*)\}[ \t]*(?:\n|$)/g;
const CLOSE = /\n[ \t]*:::[ \t]*(?=\n|$)/;

function attributes(raw: string): Record<string, string> {
    const result: Record<string, string> = {};
    for (const match of raw.matchAll(/(\w+)\s*=\s*"([^"]*)"/g)) result[match[1].toLowerCase()] = match[2];
    return result;
}

const MERMAID_FENCE = /(^|\n)[ \t]*```mermaid[ \t]*\n([\s\S]*?)\n[ \t]*```[ \t]*(?=\n|$)/g;
const DIAGRAM_TITLES: Record<string, string> = {
    flowchart: "Flowchart", graph: "Flowchart", sequencediagram: "Sequence diagram", classdiagram: "Class diagram",
    statediagram: "State diagram", "statediagram-v2": "State diagram", erdiagram: "Entity relationship diagram",
    gantt: "Gantt chart", mindmap: "Mind map", timeline: "Timeline", pie: "Pie chart", journey: "User journey",
};

/** Prose with any complete ```mermaid code blocks turned into diagram artifacts: models sometimes write a
 *  diagram as a plain code block instead of an artifact, and a diagram is more useful drawn than as source. */
function splitDiagrams(text: string, nextIndex: () => number): Segment[] {
    const segments: Segment[] = [];
    let cursor = 0;
    for (const match of text.matchAll(MERMAID_FENCE)) {
        const start = match.index + match[1].length;
        if (start > cursor) segments.push({ kind: "text", text: text.slice(cursor, start) });
        const keyword = match[2].trim().split(/\s/, 1)[0].toLowerCase();
        const title = DIAGRAM_TITLES[keyword] ?? "Diagram";
        segments.push({ kind: "artifact", key: `${title}#${nextIndex()}`, type: "mermaid", title, language: "",
            content: match[2], complete: true });
        cursor = match.index + match[0].length;
    }
    if (cursor < text.length) segments.push({ kind: "text", text: text.slice(cursor) });
    return segments;
}

/** Split an answer into prose and artifacts. An unterminated final artifact is marked incomplete. */
export function splitArtifacts(text: string): Segment[] {
    const segments: Segment[] = [];
    let cursor = 0;
    let index = 0;
    const nextIndex = () => index++;
    OPEN.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = OPEN.exec(text))) {
        const start = match.index + match[1].length;
        if (start > cursor) segments.push(...splitDiagrams(text.slice(cursor, start), nextIndex));
        const bodyStart = match.index + match[0].length;
        const rest = text.slice(bodyStart);
        const close = CLOSE.exec("\n" + rest);
        const attrs = attributes(match[2]);
        const type = (TYPES.includes(attrs.type as ArtifactType) ? attrs.type : "code") as ArtifactType;
        const title = (attrs.title || "Untitled artifact").slice(0, 120);
        const content = close ? rest.slice(0, Math.max(0, close.index - 1)) : rest;
        segments.push({ kind: "artifact", key: `${title}#${nextIndex()}`, type, title, language: attrs.language || "",
            content: stripFence(content), complete: Boolean(close) });
        if (!close) return segments;
        cursor = bodyStart + close.index - 1 + close[0].length;
        OPEN.lastIndex = cursor;
    }
    if (cursor < text.length) segments.push(...splitDiagrams(text.slice(cursor), nextIndex));
    return segments;
}

/** Models occasionally wrap artifact bodies in a code fence despite instructions. */
function stripFence(content: string): string {
    const fenced = /^\s*```[\w-]*\n([\s\S]*?)\n?```\s*$/.exec(content);
    return fenced ? fenced[1] : content;
}

/** Quote flowchart node labels that contain characters Mermaid reads as syntax, e.g. A[Review (30 days)].
 *  Models often forget; an unquoted "(" inside [ ] otherwise fails the whole diagram. */
export function repairMermaid(source: string): string {
    return source
        .replace(/(\b[\w-]+)\[(?!")([^\]\n"]*[(){}|<>][^\]\n"]*)\](?!\])/g, (_, id: string, label: string) => `${id}["${label.trim()}"]`)
        .replace(/(\b[\w-]+)\{(?!")([^}\n"]*[()[\]|<>][^}\n"]*)\}/g, (_, id: string, label: string) => `${id}{"${label.trim()}"}`);
}

const BASE_STYLE ="<style>*,*::before,*::after{box-sizing:border-box}html,body{margin:0;min-height:100%}" +
    "body{font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;color:#0f172a;background:#ffffff}</style>";
const REPORT_ERRORS = "<script>(function(){function n(m){parent.postMessage({source:'corten-artifact',type:'error',detail:String(m).slice(0,2000)},'*')}" +
    "addEventListener('error',function(e){n(e.message||'Error')});addEventListener('unhandledrejection',function(e){n(e.reason&&e.reason.message||e.reason)});" +
    "addEventListener('load',function(){parent.postMessage({source:'corten-artifact',type:'ready'},'*')})})();</script>";

function sourceScript(content: string) {
    // JSON in a non-executed script; "<" is escaped so the content can never close the tag.
    return `<script type="application/json" id="artifact-source">${JSON.stringify(content).replace(/</g, "\\u003c")}</script>`;
}

/** The complete document for an artifact's sandboxed iframe, or null for types rendered in the page. */
export function sandboxDocument(artifact: Pick<Artifact, "type" | "content">): string | null {
    const head = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">${BASE_STYLE}`;
    switch (artifact.type) {
        case "react":
            return `${head}</head><body><div id="root"></div>${sourceScript(artifact.content)}` +
                `<script src="/artifact-runtime/react-runtime.js"></script></body></html>`;
        case "html": {
            const html = artifact.content;
            if (/<head[^>]*>/i.test(html)) return html.replace(/<head[^>]*>/i, match => match + REPORT_ERRORS);
            if (/<html[^>]*>/i.test(html)) return html.replace(/<html[^>]*>/i, match => match + "<head>" + REPORT_ERRORS + "</head>");
            return `${head}${REPORT_ERRORS}</head><body>${html}</body></html>`;
        }
        case "mermaid":
            return `${head}<style>body{display:flex;justify-content:center;padding:24px}#root svg{max-width:100%;height:auto}</style></head>` +
                `<body><div id="root" role="img" aria-label="Diagram"></div>${sourceScript(repairMermaid(artifact.content))}` +
                `<script src="/artifact-runtime/mermaid.min.js"></script><script>(function(){` +
                "function n(t,d){parent.postMessage({source:'corten-artifact',type:t,detail:d||''},'*')}" +
                "var code=JSON.parse(document.getElementById('artifact-source').textContent);" +
                "mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral',fontFamily:'Inter,system-ui,sans-serif'});" +
                "mermaid.render('corten-diagram',code).then(function(r){document.getElementById('root').innerHTML=r.svg;n('ready')})" +
                ".catch(function(e){var b=document.getElementById('root');b.textContent='This diagram could not be drawn: '+(e&&e.message||e);" +
                "b.style.cssText='color:#991b1b;font:14px system-ui';n('error',String(e&&e.message||e))})})();</script></body></html>";
        case "svg":
            return `${head}<style>body{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:16px}` +
                `svg{max-width:100%;height:auto}</style></head><body>${artifact.content}</body></html>`;
        default:
            return null;
    }
}

/** Sandbox permissions: scripts only where needed, never same-origin, popups or downloads. */
export function sandboxPermissions(type: ArtifactType): string {
    return type === "svg" ? "" : "allow-scripts allow-forms allow-modals";
}

const EXTENSIONS: Record<string, string> = { react: "jsx", html: "html", mermaid: "mmd", svg: "svg", markdown: "md" };
export function artifactFilename(artifact: Pick<Artifact, "type" | "title" | "language">): string {
    const stem = artifact.title.replace(/[\\/:*?"<>|\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80) || "artifact";
    const extension = EXTENSIONS[artifact.type] ?? ({ python: "py", javascript: "js", typescript: "ts", sql: "sql",
        bash: "sh", shell: "sh", java: "java", go: "go", rust: "rs", csharp: "cs", cpp: "cpp", c: "c" }[artifact.language.toLowerCase()] ?? "txt");
    return `${stem}.${extension}`;
}

export const ARTIFACT_LABELS: Record<ArtifactType, string> = {
    react: "Interactive app", html: "Web page", mermaid: "Diagram", svg: "Graphic", markdown: "Document", code: "Code",
};
