const { test, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const load = require("./load-ts"), modules = new Map();
const research = load("src/lib/pharmaResearch.ts", modules);
const { setStorageAccount, accountStorage } = load("src/lib/accountStorage.ts", modules);
function store() { const map = new Map(); return { getItem: k => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: k => map.delete(k) }; }
const owner = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
beforeEach(() => { global.localStorage = store(); global.sessionStorage = store(); global.window = { location: { search: "" }, dispatchEvent() {} }; setStorageAccount(owner); });
const source = { url: "https://www.fda.gov/drugs/example", title: "Example", domain: "www.fda.gov", citationIndex: 1 };
const turn = { query: "Review Example", answer: "A fact [1].", sources: [source] };

test("research accepts only validated HTTPS evidence and tool states", () => {
    assert.deepEqual(research.researchSources([source, { ...source, url: "javascript:alert(1)" }, { ...source, citationIndex: 99 }]), [source]);
    assert.equal(research.researchTool({ id: "1", label: "FDA", status: "arbitrary" }), null);
    assert.equal(research.researchTool({ id: "1", label: "FDA", status: "available", count: 3 }).count, 3);
    assert.deepEqual(research.researchEvidence({ records: [{ title: "Untrusted", url: "javascript:evil" }] }).records, []);
});

test("context respects byte and message budgets without chopping scientific facts", () => {
    const messages = research.researchMessages(Array.from({ length: 30 }, () => ({ query: "你好".repeat(1500), answer: "NCT12345678 " + "x".repeat(5000) })));
    assert.ok(messages.length <= 12);
    assert.ok(messages.reduce((n, m) => n + new TextEncoder().encode(m.content).length, 0) <= 12000);
    assert.ok(messages.at(-1).content.startsWith("NCT12345678"));
});

test("evidence exports retain complete numbers, Unicode, limitations and spreadsheet safety", () => {
    const rows = [{ citation: 1, title: "=HYPERLINK(bad)", url: source.url, kind: "trial_record", facts: { enrollment: 123456, name: "药物" }, excerpt: "Quoted \"fact\"", date: "2026-10", date_meaning: "Estimated completion", retrieved_at: "2026-10-14T00:00:00Z" }];
    const csv = research.evidenceCsv(rows, [{ tool: "trials", status: "available", coverage: "Sample, not a full pipeline." }]);
    assert.ok(csv.startsWith("\ufeff")); assert.ok(csv.includes("'=HYPERLINK"));
    assert.ok(csv.includes("123456") && csv.includes("药物") && csv.includes("Estimated completion") && csv.includes("Sample, not a full pipeline."));
    const report = research.researchReport(turn.query, turn.answer, [source], []);
    assert.ok(report.includes("[1] Example") && report.includes(source.url));
});

test("research history resumes in Pharma while other conversations keep their route", () => {
    assert.equal(research.saveResearchThread([turn], [], "research-1", owner), true);
    const restored = research.restoreResearchThread("research-1");
    assert.equal(restored.answer, turn.answer);
    assert.equal(research.pharmaThreadPath(restored), "/analyst-workspace/pharma/research?id=research-1");
    assert.equal(research.pharmaThreadPath({ id: "other" }), "/search?id=other");
    assert.equal(research.pharmaThreadPath({ id: "record-chat", pharmaRecord: { id: "event:x" } }), "/analyst-workspace/pharma/event%3Ax");
    setStorageAccount("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"); assert.equal(research.restoreResearchThread("research-1"), null);
});

test("private mode, account switches, deleted chats and concurrent changes are respected", () => {
    sessionStorage.setItem("corten_private_mode", "true");
    assert.equal(research.saveResearchThread([turn], [], "private", owner), false);
    sessionStorage.removeItem("corten_private_mode");
    assert.equal(research.saveResearchThread([turn], [], "saved", owner), true);
    const changed = { ...turn, answer: "Concurrent answer." };
    assert.equal(research.saveResearchThread([changed], [changed], "saved", owner), false);
    accountStorage.setItem("corten_threads", "[]");
    assert.equal(research.saveResearchThread([turn, changed], [turn], "saved", owner), false);
    setStorageAccount(null); assert.equal(research.saveResearchThread([turn], [], "switched", owner), false);
});
