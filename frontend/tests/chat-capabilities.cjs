const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const path = require("node:path");
const load = require("./load-ts");
const original = { localStorage: global.localStorage, sessionStorage: global.sessionStorage, window: global.window };
after(() => Object.assign(global, original));

const lib = name => load(path.join(__dirname, "../src/lib", name + ".ts"));

test("artifacts are split from prose, including while still streaming", () => {
    const { splitArtifacts } = lib("artifacts");
    const answer = 'Here is the dashboard.\n:::artifact{type="react" title="Revenue Dashboard"}\nexport default function App() {}\n:::\nIt shows revenue.';
    const parts = splitArtifacts(answer);
    assert.deepEqual(parts.map(p => p.kind), ["text", "artifact", "text"]);
    assert.equal(parts[1].type, "react");
    assert.equal(parts[1].title, "Revenue Dashboard");
    assert.equal(parts[1].content, "export default function App() {}");
    assert.equal(parts[1].complete, true);
    assert.equal(parts[2].text, "\nIt shows revenue.");

    const streaming = splitArtifacts('Intro\n:::artifact{type="html" title="Page"}\n<html><body>Hel');
    assert.equal(streaming.length, 2);
    assert.equal(streaming[1].complete, false);
    assert.equal(streaming[1].content, "<html><body>Hel");

    const two = splitArtifacts(':::artifact{type="mermaid" title="Flow"}\ngraph TD;A-->B\n:::\nand\n:::artifact{type="code" language="python" title="Script"}\nprint(1)\n:::');
    assert.deepEqual(two.filter(p => p.kind === "artifact").map(p => [p.type, p.language, p.content]),
        [["mermaid", "", "graph TD;A-->B"], ["code", "python", "print(1)"]]);
    // Unknown types are shown as code; code fences inside the block are removed.
    const fenced = splitArtifacts(':::artifact{type="weird" title="X"}\n```js\nlet a = 1;\n```\n:::');
    assert.equal(fenced[0].type, "code");
    assert.equal(fenced[0].content, "let a = 1;");
    assert.deepEqual(splitArtifacts("No artifacts [1]."), [{ kind: "text", text: "No artifacts [1]." }]);
});

test("a diagram written as a plain mermaid code block is still drawn as a diagram", () => {
    const { splitArtifacts } = lib("artifacts");
    const answer = "Here is the flow:\n```mermaid\nflowchart TD\n  A --> B\n```\nThen review.\n```python\nprint(1)\n```";
    const parts = splitArtifacts(answer);
    assert.deepEqual(parts.map(p => p.kind), ["text", "artifact", "text"]);
    assert.deepEqual([parts[1].type, parts[1].title, parts[1].content, parts[1].complete], ["mermaid", "Flowchart", "flowchart TD\n  A --> B", true]);
    assert.match(parts[2].text, /```python/, "other code blocks stay in the answer");
    assert.equal(splitArtifacts("```mermaid\nsequenceDiagram\n  A->>B: Hi\n```")[0].title, "Sequence diagram");
    // While streaming, an unfinished block stays text until it closes.
    assert.deepEqual(splitArtifacts("Flow:\n```mermaid\nflowchart TD\n  A -->").map(p => p.kind), ["text"]);
    // Blocks inside an artifact belong to the artifact.
    const nested = splitArtifacts(':::artifact{type="markdown" title="Plan"}\n# Plan\n```mermaid\ngraph TD;A-->B\n```\n:::');
    assert.deepEqual(nested.map(p => [p.kind, p.type]), [["artifact", "markdown"]]);
    const keys = splitArtifacts("```mermaid\ngraph TD;A-->B\n```\n:::artifact{type=\"svg\" title=\"Logo\"}\n<svg/>\n:::\n```mermaid\npie\n```").map(p => p.key).filter(Boolean);
    assert.equal(new Set(keys).size, keys.length, "every artifact has its own key");
});

test("sandbox documents cannot be broken out of and never get same-origin access", () => {
    const { sandboxDocument, sandboxPermissions, artifactFilename } = lib("artifacts");
    const hostile = 'export default () => "</script><script>parent.document.cookie</script>";';
    const doc = sandboxDocument({ type: "react", content: hostile });
    assert.equal((doc.match(/<\/script>/g) || []).length, 2, "only the runtime's own script tags close");
    assert.match(doc, /\\u003c\/script>/);
    assert.match(doc, /\/artifact-runtime\/react-runtime\.js/);
    assert.match(sandboxDocument({ type: "html", content: "<html><head><title>x</title></head><body>hi</body></html>" }), /<head><script>/);
    assert.match(sandboxDocument({ type: "html", content: "<p>fragment</p>" }), /<body><p>fragment<\/p><\/body>/);
    assert.match(sandboxDocument({ type: "mermaid", content: "graph TD;A-->B" }), /securityLevel:'strict'/);
    assert.equal(sandboxDocument({ type: "markdown", content: "# Hi" }), null);
    for (const type of ["react", "html", "mermaid", "svg", "markdown", "code"]) {
        assert.doesNotMatch(sandboxPermissions(type), /allow-same-origin|allow-top-navigation|allow-popups/);
    }
    assert.equal(sandboxPermissions("svg"), "");
    assert.equal(artifactFilename({ type: "react", title: 'Sales: Q3 / "Final"', language: "" }), "Sales Q3 Final .jsx".replace(" .", "."));
    assert.equal(artifactFilename({ type: "code", title: "Clean", language: "Python" }), "Clean.py");
});

test("Mermaid labels with syntax characters are quoted; valid diagrams are untouched", () => {
    const { repairMermaid } = lib("artifacts");
    assert.equal(repairMermaid("H --> I[Probation Review (30-Day)]"), 'H --> I["Probation Review (30-Day)"]');
    assert.equal(repairMermaid("A{Approved? (manager)} -->|Yes| B"), 'A{"Approved? (manager)"} -->|Yes| B');
    const valid = 'flowchart TD\n  A["Already (quoted)"] --> B[Plain label]\n  B -->|Yes| C((Circle))\n  C --> D[[Subroutine]]';
    assert.equal(repairMermaid(valid), valid);
});

test("citations become source links outside code only", () => {
    const { linkCitations } = lib("citations");
    assert.equal(linkCitations("Revenue grew [1] and [2, 3]."), "Revenue grew [1](#cite-1) and [2](#cite-2)[3](#cite-3).");
    assert.equal(linkCitations("Launch date 【1】"), "Launch date [1](#cite-1)");
    assert.equal(linkCitations("Keep `arr[1]` and\n```\nx[2]\n```\nbut cite [4]"), "Keep `arr[1]` and\n```\nx[2]\n```\nbut cite [4](#cite-4)");
    assert.equal(linkCitations("A real [1](https://example.com) link"), "A real [1](https://example.com) link");
});

test("earlier attachments are sent apart from this message's, newest first and bounded", () => {
    const values = new Map();
    global.localStorage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
    global.window = new EventTarget();
    const chat = lib("chatApi");
    const ref = (id, kind = "document") => ({ id, name: id, kind, url: `/api/v1/attachments/${id}/content`, size: 1 });
    const history = [{ attachments: [ref("a"), ref("b")] }, { attachments: [ref("c"), ref("gen", "generated"), ref("pic", "image")] }];
    assert.deepEqual(chat.conversationAttachments([ref("new")], history, "What is 17 x 23?"), { attachments: ["new"], context: ["c", "a", "b"] });
    // Earlier images only join when the question is about something visual.
    assert.deepEqual(chat.conversationAttachments([], history, "Describe the chart in more detail"), { attachments: [], context: ["c", "pic", "a", "b"] });
    assert.deepEqual(chat.conversationAttachments([ref("now", "image")], history, "and this one?"), { attachments: ["now"], context: ["c", "a", "b"] });
    for (const question of ["What colour is it?", "Recreate this screenshot as a web page", "What does the bar chart show?"]) {
        assert.ok(chat.conversationAttachments([], history, question).context.includes("pic"), question);
    }
    // Asking to make a chart is not a reference to an earlier image.
    assert.ok(!chat.conversationAttachments([], history, "Build a React dashboard with a bar chart and three KPI cards").context.includes("pic"));
    // A file attached again is sent once, as part of this message.
    assert.deepEqual(chat.conversationAttachments([ref("a")], history, "again"), { attachments: ["a"], context: ["c", "b"] });
    const many = Array.from({ length: 15 }, (_, i) => ref("x" + i));
    assert.deepEqual(chat.conversationAttachments(many, history), { attachments: many.slice(0, 10).map(r => r.id), context: [] });
    assert.deepEqual(chat.conversationAttachments(many.slice(0, 8), history).context, ["c", "a"]);
    assert.equal(chat.getAnswerMode(), "auto");
    chat.setAnswerMode("think");
    assert.equal(chat.getAnswerMode(), "think");
    values.set("corten_answer_mode", "turbo");
    assert.equal(chat.getAnswerMode(), "auto");
    const file = (name, size, type = "") => ({ name, size, type });
    assert.equal(chat.attachmentProblem(file("photo.png", 10, "image/png")), null);
    assert.equal(chat.attachmentProblem(file("report.pdf", 10)), null);
    assert.match(chat.attachmentProblem(file("setup.exe", 10)), /Unsupported/);
    assert.match(chat.attachmentProblem(file("big.pdf", 26 * 1024 * 1024)), /25 MB/);
    assert.match(chat.attachmentProblem(file("empty.txt", 0)), /empty/);
});

test("question drafts carry only valid attachment references", () => {
    const session = new Map();
    global.sessionStorage = { getItem: k => session.get(k) ?? null, setItem: (k, v) => session.set(k, v) };
    global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
    const cache = new Map();
    load(path.join(__dirname, "../src/lib/accountStorage.ts"), cache).setStorageAccount("acct");
    const drafts = load(path.join(__dirname, "../src/lib/questionDrafts.ts"), cache);
    const good = { id: "1", name: "brief.pdf", kind: "document", url: "/api/v1/attachments/1/content", size: 5 };
    const bad = { id: "2", name: "x", kind: "image", url: "https://evil.example/x.png", size: 5 };
    const route = drafts.questionPath("Summarize this", "all", undefined, "search", [good, bad]);
    const id = new URLSearchParams(route.split("?")[1]).get("draft");
    assert.deepEqual(drafts.readQuestionDraft(id).attachments, [good]);
});

test("questions send mode, attachments and private status to the answer service", async () => {
    const { openSearchStream } = lib("searchConnection");
    const bodies = [];
    const fetcher = async (url, options = {}) => {
        if (url.endsWith("/status")) return Response.json({ status: "ready" });
        bodies.push(JSON.parse(options.body));
        return new Response("data: {}\n\n");
    };
    const signal = new AbortController().signal;
    await openSearchStream({ apiBase: "", query: "q", focus: "all", messages: [], mode: "think", attachments: ["a1"],
        contextAttachments: ["e1"], incognito: true }, signal, () => {}, { fetcher });
    await openSearchStream({ apiBase: "", query: "q", focus: "all", messages: [], mode: "auto", attachments: [], contextAttachments: [] }, signal, () => {}, { fetcher });
    assert.deepEqual([bodies[0].mode, bodies[0].attachments, bodies[0].context_attachments, bodies[0].incognito], ["think", ["a1"], ["e1"], true]);
    assert.ok(!("mode" in bodies[1]) && !("attachments" in bodies[1]) && !("context_attachments" in bodies[1]) && !("incognito" in bodies[1]));
});
