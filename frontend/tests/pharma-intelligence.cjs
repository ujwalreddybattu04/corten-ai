const { test } = require("node:test");
const assert = require("node:assert/strict");
const { parsePharmaFeed, pharmaOverview, PHARMA_SOURCE_LABELS } = require("./load-ts")("src/lib/pharmaFeed.ts");
test("seven-source events validate version, impact, identity and UTC chart grouping", () => {
  const item = { id: "event:" + "a".repeat(64), source: "ema", title: "Example", summary: "EU action", category: "Regulatory", organization: "Example", url: "https://www.ema.europa.eu/en/medicines", date: "2026-10-14", date_label: "European Commission decision", tags: [],
    version: "b".repeat(64), impact: { rating: "Material", rationale: "Review action", policy_version: "events-1", basis: "source_rules" }, event: { kind: "ema_authorisation", label: "EU authorisation", date: "2026-10-14", date_label: "Decision", baseline: true, changes: [], reason: null }, drugs: [{ id: "c".repeat(64), name: "ingredient", evidence_url: "https://www.ema.europa.eu/en/medicines" }] };
  const feed = { schema_version: 2, topic: "all", days: 7, since: "2026-10-08", until: "2026-10-14", checked_at: "2026-10-14T00:00:00Z", next_check_at: "2026-10-14T00:15:00Z", status: "available", partial: false, limit_per_source: 20, items: [item],
    sources: Object.keys(PHARMA_SOURCE_LABELS).map(id => ({ id, name: id, url: "https://example.com", cadence: "Periodic", scope: "Public", status: id === "ema" ? "available" : "empty", checked_at: "2026-10-14T00:00:00Z", source_updated_at: null, items: id === "ema" ? [item] : [] })) };
  assert.equal(parsePharmaFeed(feed, "all", 7).items.length, 1);
  assert.equal(pharmaOverview(feed).bins.reduce((s,b) => s+b.fda+b.trials+b.news,0), 1);
  for (const mutate of [i => i.impact.rating = "High", i => i.event.date = "2026-10-13", i => i.drugs[0].evidence_url = "javascript:bad", i => i.version = "invalid"]) {
    const bad = structuredClone(feed); mutate(bad.items[0]); bad.sources.find(s => s.id === "ema").items = bad.items;
    assert.throws(() => parsePharmaFeed(bad, "all", 7));
  }
});
