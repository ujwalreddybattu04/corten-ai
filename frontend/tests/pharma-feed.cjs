const { test } = require("node:test");
const assert = require("node:assert/strict");
const { parsePharmaFeed, requestPharmaFeed, filterPharmaItems, pharmaCsv, retainPharmaFeed } = require("./load-ts")("src/lib/pharmaFeed.ts");
function payload() {
  const today = new Date().toISOString().slice(0, 10);
  const item = { id: "fda:example", source: "fda", title: "Drug update", summary: "Example Pharma. New action.", organization: "Example Pharma", date: today, date_label: "FDA action date", category: "Regulatory", url: "https://www.accessdata.fda.gov/example", tags: ["NDA123456"], details: { ingredients: ["Example ingredient"] } };
  const sources = ["fda", "trials", "news"].map(id => ({ id, name: id, url: "https://example.com", cadence: "Daily", scope: "US records", status: id === "fda" ? "available" : "empty", items: id === "fda" ? [item] : [], checked_at: new Date().toISOString(), source_updated_at: null }));
  return { topic: "all", days: 7, since: today, until: today, checked_at: new Date().toISOString(), next_check_at: new Date(Date.now() + 3600_000).toISOString(), status: "available", partial: false, limit_per_source: 20, items: [item], sources };
}
test("rejects wrong therapy, inconsistent source records, unsafe URLs and invalid dates", () => {
  assert.equal(parsePharmaFeed(payload(), "all", 7).items.length, 1);
  for (const mutate of [f => f.topic = "oncology", f => f.items[0].url = "javascript:alert(1)", f => f.items[0].url = "https://user:password@example.com", f => f.items[0].date = "2026-99-01", f => f.sources[0].items = [], f => f.sources[1] = null, f => f.items.push(f.items[0])]) {
    const feed = payload(); mutate(feed);
    assert.throws(() => parsePharmaFeed(feed, "all", 7));
  }
});
test("search matches sponsor, study tags and interventions within the loaded source", () => {
  const feed = payload();
  assert.equal(filterPharmaItems(feed.items, "all", "pharma ingredient").length, 1);
  assert.equal(filterPharmaItems(feed.items, "trials", "pharma").length, 0);
  assert.equal(filterPharmaItems(feed.items, "all", "NDA123456").length, 1);
  assert.equal(filterPharmaItems(feed.items, "all", "missing").length, 0);
});
test("CSV exports quoted Unicode, formula-safe text, source dates and FDA's true coverage", () => {
  const feed = payload(); feed.topic = "oncology";
  feed.items[0].title = '=HYPERLINK("https://example.com")';
  feed.items[0].organization = "研究, Pharma";
  const csv = pharmaCsv(feed.items, feed);
  assert.ok(csv.startsWith("\uFEFF"));
  assert.ok(csv.includes('"\'=HYPERLINK(""https://example.com"")"'));
  assert.ok(csv.includes('"研究, Pharma"'));
  assert.ok(csv.includes('"available","all","US records"'));
  assert.ok(csv.includes(feed.sources[0].checked_at));
});
test("outage retention labels stale data and expires without renewing source time", () => {
  const feed = payload();
  const retained = retainPharmaFeed(feed);
  assert.equal(retained.sources[0].status, "stale");
  assert.equal(retained.sources[0].checked_at, feed.sources[0].checked_at);
  assert.equal(retained.items.length, 1);
  assert.equal(retainPharmaFeed(retained, Date.now() + 24 * 3600_000 + 1), null);
});
test("read-only retry recovers after transient failure without leaking error bodies", async () => {
  let calls = 0, notices = 0;
  const feed = await requestPharmaFeed("all", 7, new AbortController().signal, () => notices++, {
    budgetMs: 4000, fetcher: async url => { assert.ok(url.endsWith("topic=all&days=7")); return ++calls === 1 ? new Response("private provider information", { status: 502 }) : Response.json(payload()); },
  });
  assert.equal(feed.items.length, 1); assert.equal(calls, 2); assert.equal(notices, 1);
});
test("permanent errors and malformed successful feeds fail without repeated requests", async () => {
  for (const response of [new Response("secret error", { status: 422 }), Response.json({ topic: "unknown" })]) {
    let calls = 0;
    await assert.rejects(requestPharmaFeed("all", 7, new AbortController().signal, undefined, { fetcher: async () => { calls++; return response; } }), error => !error.message.includes("secret"));
    assert.equal(calls, 1);
  }
});
test("Retry-After exceeding the budget prevents an early retry", async () => {
  let calls = 0;
  await assert.rejects(requestPharmaFeed("all", 7, new AbortController().signal, undefined, { budgetMs: 100, fetcher: async () => { calls++; return new Response("", { status: 503, headers: { "Retry-After": "60" } }); } }));
  assert.equal(calls, 1);
});
test("switching tabs cancels a pending retry", async () => {
  const controller = new AbortController(); let calls = 0;
  await assert.rejects(requestPharmaFeed("all", 7, controller.signal, () => controller.abort(), { fetcher: async () => { calls++; throw new TypeError("offline"); } }));
  assert.equal(calls, 1);
});
