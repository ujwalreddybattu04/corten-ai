const { test, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const loadTs = require("./load-ts");
const modules = new Map();
const { readSavedFeed, saveFeed, requestDiscoverFeed } = loadTs("src/lib/discoverFeed.ts", modules);
const { setStorageAccount } = loadTs("src/lib/accountStorage.ts", modules);
const article = { id: "story", title: "Research news", url: "https://example.com/story", source: { name: "Example" } };
const payload = () => ({ articles: [article], has_more: false, status: "available", fetched_at: new Date().toISOString() });
beforeEach(() => {
    const values = new Map();
    global.localStorage = { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
    setStorageAccount(null);
});
test("saved stories retain their age and expire even when served repeatedly", () => {
    const feed = payload();
    saveFeed("top", feed);
    const saved = readSavedFeed("top");
    assert.equal(saved.status, "stale");
    assert.equal(saved.fetched_at, feed.fetched_at);
    saveFeed("top", saved);
    assert.equal(readSavedFeed("top", Date.now() + 6 * 60 * 60 * 1000 + 1), null);
    assert.equal(readSavedFeed("technology"), null);
});
test("feed storage stays within the verified personal account", () => {
    setStorageAccount("account-a"); saveFeed("top", payload());
    setStorageAccount("account-b"); assert.equal(readSavedFeed("top"), null);
    setStorageAccount(null); assert.equal(readSavedFeed("top"), null);
    setStorageAccount("account-a"); assert.equal(readSavedFeed("top").articles.length, 1);
});
test("partial refresh and unavailable browser storage do not overwrite the last good feed", () => {
    saveFeed("top", payload());
    saveFeed("top", { ...payload(), articles: [{ ...article, title: "Incomplete" }], partial: true });
    assert.equal(readSavedFeed("top").articles[0].title, "Research news");
    global.localStorage.getItem = () => { throw Error("denied"); };
    assert.equal(readSavedFeed("top"), null);
    global.localStorage.setItem = () => { throw Error("quota"); };
    assert.doesNotThrow(() => saveFeed("top", payload()));
});
test("a temporary backend failure is retried and recovers", async () => {
    let calls = 0, notices = 0;
    const result = await requestDiscoverFeed("/feed", new AbortController().signal, () => notices++, {
        budgetMs: 3000, fetcher: async () => ++calls === 1 ? new Response("", { status: 502 }) : Response.json(payload()),
    });
    assert.equal(result.articles.length, 1); assert.equal(calls, 2); assert.equal(notices, 1);
});
test("invalid requests and malformed successful data stop immediately", async () => {
    for (const response of [new Response("", { status: 422 }), Response.json({ articles: [{ url: "javascript:alert(1)" }], status: "available" })]) {
        let calls = 0;
        await assert.rejects(requestDiscoverFeed("/feed", new AbortController().signal, undefined, {
            fetcher: async () => { calls++; return response; },
        }));
        assert.equal(calls, 1);
    }
});
test("Retry-After longer than the deadline is respected instead of hammering the provider", async () => {
    let calls = 0;
    await assert.rejects(requestDiscoverFeed("/feed", new AbortController().signal, undefined, {
        budgetMs: 200, fetcher: async () => { calls++; return new Response("", { status: 503, headers: { "Retry-After": "30" } }); },
    }));
    assert.equal(calls, 1);
});
test("cancelling a tab switch stops a pending retry", async () => {
    const controller = new AbortController(); let calls = 0;
    const pending = requestDiscoverFeed("/feed", controller.signal, () => controller.abort(), {
        fetcher: async () => { calls++; throw new TypeError("Network unavailable"); },
    });
    await assert.rejects(pending); assert.equal(calls, 1);
});
test("attempt timeout is bounded even when a fetch never returns", async () => {
    // Keep Node alive while AbortSignal's unref'ed timeout fires.
    const keepAlive = setTimeout(() => {}, 500);
    try {
        await assert.rejects(requestDiscoverFeed("/feed", new AbortController().signal, undefined, {
            budgetMs: 50, attemptMs: 20, fetcher: (_url, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(signal.reason))),
        }));
    } finally { clearTimeout(keepAlive); }
});
