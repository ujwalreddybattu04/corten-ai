const { test, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const load = require("./load-ts"), modules = new Map();
const records = load("src/lib/pharmaRecord.ts", modules);
const { setStorageAccount, accountStorage } = load("src/lib/accountStorage.ts", modules);
function store() { const map = new Map(); return { getItem: key => map.get(key) ?? null, setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key) }; }
const owner = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
beforeEach(() => { global.localStorage = store(); global.sessionStorage = store(); global.window = { location: { search: "" }, dispatchEvent: () => {} }; setStorageAccount(owner); });
function fixture(id = "trial:NCT12345678", topic = "all") {
    const now = new Date().toISOString(), day = now.slice(0, 10);
    const item = { id, source: "trials", title: "Study of Example medicine", summary: "A recruiting study; no reported results.", organization: "Example Pharma", date: day, date_label: "Record updated", category: "Clinical trials", url: "https://clinicaltrials.gov/study/NCT12345678", tags: ["Phase 3"], details: { study_id: "NCT12345678", phases: ["PHASE3"], conditions: ["Cancer"], status: "RECRUITING" } };
    const sources = ["fda", "trials", "news"].map(id => ({ id, name: id, url: "https://example.com", cadence: "Daily", scope: "Records", status: id === "trials" ? "available" : "empty", checked_at: now, source_updated_at: null, items: id === "trials" ? [item] : [] }));
    const feed = { topic, days: 7, since: day, until: day, checked_at: now, next_check_at: now, status: "available", partial: true, limit_per_source: 20, sources, items: [item] };
    return { item, feed };
}
test("canonical record links encode identifiers and contain only public filters", () => {
    const r = fixture("fda:NDA123456:SUPPL:001");
    assert.equal(records.pharmaRecordPath(r.item, r.feed), "/analyst-workspace/pharma/fda%3ANDA123456%3ASUPPL%3A001?topic=all&days=7");
    assert.deepEqual(records.pharmaFilters("?topic=evil&days=365&source=private"), { topic: "all", days: 7, source: "all" });
    assert.equal(sessionStorage.getItem("corten_pharma_records_v1"), null, "rendering a link has no storage side effects");
});

test("phase labels are readable while scientific names and identifiers stay verbatim", () => {
    assert.equal(records.pharmaFieldText("phases", ["EARLY_PHASE1", "PHASE2"]), "Early Phase 1 · Phase 2");
    assert.equal(records.pharmaFieldText("ingredients", ["PHASEOLUS VULGARIS", "中文药名"]), "PHASEOLUS VULGARIS · 中文药名");
    assert.equal(records.pharmaFieldText("study_id", "NCT12345678"), "NCT12345678");
    assert.equal(records.pharmaFieldText("phases", ["UNKNOWN"]), "UNKNOWN");
    assert.equal(records.pharmaFieldText("ingredients", []), "Not listed");
});
test("record snapshots enforce account ownership, exact filters and age", () => {
    const r = fixture("cache:owner"); records.rememberPharmaRecord(r.item, r.feed);
    assert.equal(records.readPharmaRecord(r.item.id, "all", 7).item.id, r.item.id);
    assert.equal(records.readPharmaRecord(r.item.id, "oncology", 7), null);
    setStorageAccount("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
    assert.equal(records.readPharmaRecord(r.item.id, "all", 7), null);
    const expired = fixture("cache:expired");
    sessionStorage.setItem("corten_pharma_records_v1", JSON.stringify([{ owner: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", created: Date.now() - 25 * 3600_000, feed: expired.feed }]));
    assert.equal(records.readPharmaRecord(expired.item.id, "all", 7), null);
});
test("a different or corrupt cached feed does not hide a later valid record", () => {
    const good = fixture("cache:valid"), wrong = fixture("cache:other", "oncology"), bad = fixture("cache:bad"); bad.feed.sources = [];
    sessionStorage.setItem("corten_pharma_records_v1", JSON.stringify([wrong, bad, good].map(r => ({ owner, created: Date.now(), feed: r.feed }))));
    assert.equal(records.readPharmaRecord(good.item.id, "all", 7).item.id, good.item.id);
    assert.equal(records.readPharmaRecord(bad.item.id, "all", 7), null);
});
test("model evidence preserves source facts and dates within the API history limit", () => {
    const r = fixture(); const evidence = records.pharmaEvidence(r);
    const body = JSON.parse(evidence.slice(evidence.indexOf("{")));
    assert.equal(body.details.study_id, "NCT12345678"); assert.equal(body.date_meaning, "Record updated");
    assert.deepEqual(body.details.phases, ["PHASE3"]); assert.equal(body.url, r.item.url);
    r.item.summary = "\\".repeat(1200); r.item.title = "\u0000".repeat(1200); r.item.url += "\u0000".repeat(3000);
    const bounded = records.pharmaEvidence(r); assert.ok(bounded.length <= 6000); JSON.parse(bounded.slice(bounded.indexOf("{")));
    const context = records.pharmaEvidence(r); assert.ok(context.length <= 6000); JSON.parse(context.slice(context.indexOf("{")));
    r.item.id = "\u0000".repeat(240); r.feed.sources[1].name = "\u0000".repeat(160);
    for (const field of ["title", "summary", "organization", "date_label"]) r.item[field] = "\u0000".repeat(1200);
    const hostile = records.pharmaEvidence(r); assert.ok(hostile.length <= 6000); JSON.parse(hostile.slice(hostile.indexOf("{")));
});
test("completed analyses and follow-ups use the native chat schema and resume", () => {
    const r = fixture(), source = records.pharmaOriginalSource(r), id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
    const first = [{ query: records.pharmaDisplayQuery(r), answer: "Study summary [1].", sources: [source] }];
    assert.equal(records.savePharmaThread(r, first, [], id, owner), true);
    const rows = JSON.parse(accountStorage.getItem("corten_threads")); rows[0].title = "My trial review"; accountStorage.setItem("corten_threads", JSON.stringify(rows));
    const next = [...first, { query: "What is the phase?", answer: "Phase 3.", sources: [source] }];
    assert.equal(records.savePharmaThread(r, next, first, id, owner), true);
    const restored = records.restorePharmaThread(r); assert.equal(restored.title, "My trial review");
    assert.equal(restored.history[0].query, first[0].query); assert.equal(restored.query, "What is the phase?");
    assert.equal(restored.sources[0].citationIndex, 1);
});

test("legacy answer pipelines remain in personal history but are not reused as the current brief", () => {
    const r = fixture(), turns = [{ query: records.pharmaDisplayQuery(r), answer: "Legacy brief", sources: [records.pharmaOriginalSource(r)] }];
    records.savePharmaThread(r, turns, [], "legacy", owner);
    const rows = JSON.parse(accountStorage.getItem("corten_threads")); delete rows[0].pharmaRecord.analysisVersion;
    accountStorage.setItem("corten_threads", JSON.stringify(rows));
    assert.equal(records.restorePharmaThread(r), null);
    assert.equal(JSON.parse(accountStorage.getItem("corten_threads"))[0].answer, "Legacy brief");
});

test("refresh shows the latest brief and its follow-ups without deleting the earlier conversation", () => {
    const history = [
        { query: "Initial analysis", answer: "Old", sources: [] },
        { query: "Earlier question", answer: "Earlier", sources: [] },
        { query: records.PHARMA_REFRESH_LABEL, answer: "Current", sources: [] },
        { query: "Current question", answer: "Current reply", sources: [] },
    ];
    assert.deepEqual(records.currentPharmaTurns(history).map(t => t.answer), ["Current", "Current reply"]);
    assert.equal(history.length, 4);
    assert.deepEqual(records.currentPharmaTurns(history.slice(0, 2)), history.slice(0, 2));
});
test("private mode, changed owner, deletion and concurrent edits never overwrite chats", () => {
    const r = fixture(), turns = [{ query: records.pharmaDisplayQuery(r), answer: "Summary", sources: [records.pharmaOriginalSource(r)] }], id = "safe";
    sessionStorage.setItem("corten_private_mode", "true"); assert.equal(records.savePharmaThread(r, turns, [], id, owner), false);
    sessionStorage.removeItem("corten_private_mode"); setStorageAccount("other"); assert.equal(records.savePharmaThread(r, turns, [], id, owner), false); setStorageAccount(owner);
    assert.equal(records.savePharmaThread(r, turns, [], id, owner), true);
    const rows = JSON.parse(accountStorage.getItem("corten_threads")); rows[0].answer = "Edited elsewhere"; accountStorage.setItem("corten_threads", JSON.stringify(rows));
    assert.equal(records.savePharmaThread(r, [...turns, turns[0]], turns, id, owner), false);
    assert.equal(JSON.parse(accountStorage.getItem("corten_threads"))[0].answer, "Edited elsewhere");
    accountStorage.setItem("corten_threads", "[]"); assert.equal(records.savePharmaThread(r, [...turns, turns[0]], turns, id, owner), false);
    assert.equal(accountStorage.getItem("corten_threads"), "[]");
});
test("a changed study field generates a new analysis, while a freshness check alone resumes", () => {
    const r = fixture(), turns = [{ query: records.pharmaDisplayQuery(r), answer: "Summary", sources: [records.pharmaOriginalSource(r)] }];
    records.savePharmaThread(r, turns, [], "fingerprint", owner);
    r.feed.sources[1].checked_at = new Date(Date.now() + 3600_000).toISOString();
    assert.ok(records.restorePharmaThread(r));
    r.item.details.phases = ["PHASE4"];
    assert.equal(records.restorePharmaThread(r), null);
});
test("corrupt conversation entries cannot hide or crash a valid saved analysis", () => {
    const r = fixture(), turns = [{ query: records.pharmaDisplayQuery(r), answer: "Summary", sources: [records.pharmaOriginalSource(r)] }];
    records.savePharmaThread(r, turns, [], "valid", owner);
    const rows = JSON.parse(accountStorage.getItem("corten_threads"));
    accountStorage.setItem("corten_threads", JSON.stringify([null, { ...rows[0], history: [null] }, ...rows]));
    assert.equal(records.restorePharmaThread(r).id, "valid");
});
