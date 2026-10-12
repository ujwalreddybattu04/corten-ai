const { test } = require("node:test");
const assert = require("node:assert/strict");
const { parsePharmaFeed, requestPharmaFeed, filterPharmaItems, pharmaCsv, retainPharmaFeed, pharmaOverview, pharmaThumbnail } = require("./load-ts")("src/lib/pharmaFeed.ts");
function payload() {
  const today = new Date().toISOString().slice(0, 10);
  const item = { id: "fda:example", source: "fda", title: "Drug update", summary: "Example Pharma. New action.", organization: "Example Pharma", date: today, date_label: "FDA action date", category: "Regulatory", url: "https://www.accessdata.fda.gov/example", tags: ["NDA123456"], details: { ingredients: ["Example ingredient"] } };
  const sources = ["fda", "trials", "news"].map(id => ({ id, name: id, url: "https://example.com", cadence: "Daily", scope: "US records", status: id === "fda" ? "available" : "empty", items: id === "fda" ? [item] : [], checked_at: new Date().toISOString(), source_updated_at: null }));
  return { topic: "all", days: 7, since: today, until: today, checked_at: new Date().toISOString(), next_check_at: new Date(Date.now() + 3600_000).toISOString(), status: "available", partial: false, limit_per_source: 20, items: [item], sources };
}
test("overview conserves all loaded records across UTC windows and does not double-count combined phases", () => {
  const feed = payload(); feed.since = "2026-09-13"; feed.until = "2026-10-12"; feed.days = 30;
  feed.items = [0, 1, 4, 7, 15, 25, 29].map((day, n) => ({ ...feed.items[0], id: String(n),
    date: new Date(Date.UTC(2026, 8, 13 + day)).toISOString().slice(0, 10), source: n % 2 ? "trials" : "fda",
    details: { phases: ["PHASE2", "PHASE3"] } }));
  const result = pharmaOverview(feed);
  assert.equal(result.bins.reduce((sum, b) => sum + b.fda + b.trials + b.news, 0), 7);
  assert.deepEqual(result.phases, [{ label: "Phase 2 / Phase 3", count: 3 }]);
  assert.equal(result.organizations, 1);
  for (const item of feed.items) {
    const matching = result.bins.filter((bin, i) => item.date >= bin.date && (!result.bins[i + 1] || item.date < result.bins[i + 1].date));
    assert.equal(matching.length, 1);
  }
  const single = pharmaOverview(payload()); assert.equal(single.bins.length, 1);
});
test("publisher thumbnails reject private hosts, embedded credentials and malformed values", () => {
  assert.equal(pharmaThumbnail("https://i.guim.co.uk/img/media/photo.jpg"), "https://i.guim.co.uk/img/media/photo.jpg");
  for (const value of [undefined, false, "http://i.guim.co.uk/image", "https://i.guim.co.uk.evil.test/image", "https://user:pass@i.guim.co.uk/image", "https://127.0.0.1/photo", "https://i.guim.co.uk:8443/image", "data:image/svg+xml,test", "https://i.guim.co.uk/" + "x".repeat(2100)]) assert.equal(pharmaThumbnail(value), null);
});
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
