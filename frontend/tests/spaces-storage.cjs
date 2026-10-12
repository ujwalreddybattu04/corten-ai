const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const load = require("./load-ts");
const original = global.localStorage;
after(() => { global.localStorage = original; });

function setup() {
    const values = new Map();
    global.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
    const cache = new Map();
    const storage = load(path.join(__dirname, "../src/lib/accountStorage.ts"), cache);
    const spaces = load(path.join(__dirname, "../src/lib/spaces.ts"), cache);
    const api = load(path.join(__dirname, "../src/lib/spacesApi.ts"), cache);
    return { ...storage, ...spaces, ...api };
}

test("legacy browser Spaces are prepared for one account with only safe, bounded fields", () => {
    const s = setup();
    s.setStorageAccount("account-a");
    s.accountStorage.setItem("corten_threads", JSON.stringify([{ id: "t1", title: "Saved" }, { id: "t2", title: "Other" }]));
    s.accountStorage.setItem("corten_spaces", JSON.stringify([
        { id: "sp_one", name: " Research ", icon: "<img>", color: "red", threadIds: ["t1", "t1", "missing"],
          links: ["example.org", "javascript:alert(1)", "https://u:p@evil.test", "https://example.org/"], instructions: "x".repeat(9000) },
        { id: "bad id", name: "Unsafe id" }, { id: "sp_blank", name: "   " }, null, "text",
    ]));
    const prepared = s.legacyBrowserSpaces();
    assert.equal(prepared.length, 1);
    const [space] = prepared;
    assert.equal(space.name, "Research");
    assert.equal(space.icon, "bookmark");
    assert.equal(space.color, "#6366f1");
    assert.deepEqual(space.links, ["https://example.org/"]);
    assert.equal(space.instructions.length, 8000);
    assert.deepEqual(space.threads.map(thread => thread.id), ["t1"]);
    s.setStorageAccount("account-b");
    assert.deepEqual(s.legacyBrowserSpaces(), []);
});

test("only Spaces the server confirmed are removed from the device", () => {
    const s = setup();
    s.setStorageAccount("account-a");
    s.accountStorage.setItem("corten_spaces", JSON.stringify([{ id: "sp_a", name: "A" }, { id: "sp_b", name: "B" }]));
    s.clearLegacyBrowserSpaces(["sp_a"]);
    assert.deepEqual(JSON.parse(s.accountStorage.getItem("corten_spaces")).map(item => item.id), ["sp_b"]);
    s.clearLegacyBrowserSpaces(["sp_b"]);
    assert.equal(s.accountStorage.getItem("corten_spaces"), null);
});

test("links, roles and sizes are normalized consistently with the server", () => {
    const s = setup();
    assert.equal(s.normalizeLink("example.com/reports"), "https://example.com/reports");
    assert.equal(s.normalizeLink("HTTP://Example.com"), "http://example.com/");
    for (const unsafe of ["javascript:alert(1)", "localhost", "https://user:pass@example.com", "ftp://example.com", ""]) {
        assert.equal(s.normalizeLink(unsafe), null, unsafe);
    }
    assert.equal(s.linkHost("https://www.example.org/a"), "example.org");
    assert.equal(s.canEdit("owner"), true);
    assert.equal(s.canEdit("editor"), true);
    assert.equal(s.canEdit("viewer"), false);
    assert.equal(s.canEdit(null), false);
    assert.equal(s.formatBytes(512), "512 B");
    assert.equal(s.formatBytes(1536), "1.5 KB");
    assert.equal(s.formatBytes(25 * 1024 * 1024), "25.0 MB");
    assert.equal(s.relativeTime(Date.now() - 10_000), "Just now");
});

test("Space screens use the shared Space API instead of browser-only records", () => {
    for (const file of ["page.tsx", "[id]/page.tsx", "templates/page.tsx", "join/[token]/page.tsx"]) {
        const source = fs.readFileSync(path.join(__dirname, "../src/app/spaces", file), "utf8");
        assert.doesNotMatch(source, /localStorage\.(getItem|setItem)|accountStorage\.setItem\(["']corten_spaces/, file);
    }
    for (const file of ["components/thread/ThreadMenu.tsx", "components/spaces/SaveArticleModal.tsx", "hooks/useSearch.ts"]) {
        const source = fs.readFileSync(path.join(__dirname, "../src", file), "utf8");
        assert.match(source, /spacesApi/, file);
        assert.doesNotMatch(source, /corten_spaces/, file);
    }
});

test("questions asked in a Space send its identifier to the answer service", async () => {
    const cache = new Map();
    const { openSearchStream } = load(path.join(__dirname, "../src/lib/searchConnection.ts"), cache);
    const bodies = [];
    const fetcher = async (url, options = {}) => {
        if (url.endsWith("/status")) return Response.json({ status: "ready" });
        bodies.push(JSON.parse(options.body));
        return new Response("data: {}\n\n");
    };
    await openSearchStream({ apiBase: "", query: "q", focus: "all", messages: [], spaceId: "space-1" }, new AbortController().signal, () => {}, { fetcher });
    await openSearchStream({ apiBase: "", query: "q", focus: "all", messages: [] }, new AbortController().signal, () => {}, { fetcher });
    assert.equal(bodies[0].space_id, "space-1");
    assert.equal("space_id" in bodies[1], false);

    const denied = async (url) => url.endsWith("/status") ? Response.json({ status: "ready" })
        : Response.json({ detail: "Only editors and the owner can do this. Ask the owner for edit access." }, { status: 403 });
    await assert.rejects(() => openSearchStream({ apiBase: "", query: "q", focus: "all", messages: [], spaceId: "s" },
        new AbortController().signal, () => {}, { fetcher: denied }), /Ask the owner for edit access/);
});
