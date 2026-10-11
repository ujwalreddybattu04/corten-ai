const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const path = require("node:path");
const load = require("./load-ts");
const originalFetch = global.fetch;
after(() => { global.fetch = originalFetch; });
const apiModule = () => load(path.join(__dirname, "../src/lib/api.ts"));

test("concurrent expired requests rotate once and retry every request", async () => {
    const { api } = apiModule();
    let refreshed = false, rotations = 0;
    global.fetch = async (url, options) => {
        assert.equal(options.credentials, "same-origin");
        if (url.endsWith("/refresh")) {
            rotations++;
            await new Promise(resolve => setTimeout(resolve, 10));
            refreshed = true;
            return Response.json({ token_type: "bearer" });
        }
        return refreshed ? Response.json({ id: "account-a" }) : Response.json({ detail: "Expired" }, { status: 401 });
    };
    const results = await Promise.all(Array.from({ length: 8 }, () => api.get("/api/v1/auth/me")));
    assert.equal(rotations, 1);
    assert.ok(results.every(user => user.id === "account-a"));
});

test("wrong passwords do not attempt token refresh", async () => {
    const { api } = apiModule();
    let calls = 0;
    global.fetch = async () => { calls++; return Response.json({ detail: "Invalid email or password" }, { status: 401 }); };
    await assert.rejects(api.post("/api/v1/auth/login", {}), error => error.status === 401);
    assert.equal(calls, 1);
});

test("multipart uploads retry after session refresh with original file bytes and no JSON content type", async () => {
    const { api } = apiModule();
    const body = new FormData();
    body.append("file", new Blob(["year,V\n1,25%"], { type: "text/csv" }), "input.csv");
    let uploads = 0, rotations = 0;
    global.fetch = async (url, options) => {
        if (url.endsWith("/refresh")) { rotations++; return Response.json({}); }
        uploads++;
        assert.equal(options.body, body);
        assert.equal(options.headers.get("Content-Type"), null);
        assert.equal(await options.body.get("file").text(), "year,V\n1,25%");
        return uploads === 1 ? Response.json({ detail: "Expired" }, { status: 401 }) : Response.json({ columns: ["V"] });
    };
    assert.deepEqual(await (await api.upload("/api/v1/interpolation/preview", body)).json(), { columns: ["V"] });
    assert.equal(uploads, 2);
    assert.equal(rotations, 1);
});

test("expired refresh ends the session once without retry loops", async () => {
    const { api } = apiModule();
    let calls = 0, events = 0;
    global.window = { dispatchEvent: () => events++ };
    global.fetch = async () => { calls++; return Response.json({ detail: "Signed out" }, { status: 401 }); };
    await assert.rejects(api.get("/api/v1/users/me"), error => error.status === 401);
    assert.equal(calls, 2);
    assert.equal(events, 1);
});

test("session-store outages remain recoverable errors rather than invalid credentials", async () => {
    const { api } = apiModule();
    global.fetch = async url => Response.json({ detail: "Authentication temporarily unavailable" }, { status: url.endsWith("/refresh") ? 503 : 401 });
    await assert.rejects(api.get("/api/v1/auth/me"), error => error.status === 503);
});

test("logout during refresh prevents retrying a private request", async () => {
    const { api, invalidateSessionRequests } = apiModule();
    let calls = 0;
    global.fetch = async url => {
        calls++;
        if (url.endsWith("/refresh")) { invalidateSessionRequests(); return Response.json({}); }
        return Response.json({ detail: "Expired" }, { status: 401 });
    };
    await assert.rejects(api.get("/api/v1/threads"), error => error.status === 401);
    assert.equal(calls, 2);
});

test("validation errors produce readable messages instead of object strings", () => {
    const { errorMessage } = apiModule();
    assert.equal(errorMessage({ detail: [{ msg: "Value error, Password must be at least 8 characters" }] }), "Password must be at least 8 characters");
    assert.doesNotMatch(errorMessage({ detail: {} }), /object Object/);
});

test("browser histories and analyst projects remain separate across accounts and guest mode", () => {
    const { accountStorage, setStorageAccount } = load(path.join(__dirname, "../src/lib/accountStorage.ts"));
    const values = new Map();
    global.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
    for (const key of ["corten_threads", "corten_spaces", "corten_analyst_projects_v1"]) {
        setStorageAccount(null); accountStorage.setItem(key, "guest");
        setStorageAccount("a"); assert.equal(accountStorage.getItem(key), null); accountStorage.setItem(key, "account-a");
        setStorageAccount("b"); assert.equal(accountStorage.getItem(key), null); accountStorage.setItem(key, "account-b");
        setStorageAccount("a"); assert.equal(accountStorage.getItem(key), "account-a");
        setStorageAccount(null); assert.equal(accountStorage.getItem(key), "guest");
    }
});

test("post-login redirects accept local paths and reject external or encoded traversal", () => {
    const { safeReturnPath } = load(path.join(__dirname, "../src/lib/accountStorage.ts"));
    for (const value of [null, "https://evil.example", "//evil.example", "/\\evil.example", "/auth/login", "/%61uth/login"]) assert.equal(safeReturnPath(value), "/");
    assert.equal(safeReturnPath("/analyst-workspace?tab=projects"), "/analyst-workspace?tab=projects");
});

test("legacy signed-in browser records stay hidden from guests and other accounts after token migration", () => {
    const { accountStorage, setStorageAccount, protectLegacyAccountData } = load(path.join(__dirname, "../src/lib/accountStorage.ts"));
    const id = "c60e0718-a5f8-4869-b94c-11808cefa242";
    const values = new Map([["corten_user", JSON.stringify({ id })], ["corten_threads", "legacy-private"]]);
    global.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
    protectLegacyAccountData();
    values.delete("corten_user");
    assert.equal(accountStorage.getItem("corten_threads"), null);
    accountStorage.setItem("corten_threads", "new-guest");
    setStorageAccount("other-user"); assert.equal(accountStorage.getItem("corten_threads"), null);
    setStorageAccount(id); assert.equal(accountStorage.getItem("corten_threads"), "legacy-private");
    accountStorage.setItem("corten_threads", "updated-private");
    setStorageAccount(null); assert.equal(accountStorage.getItem("corten_threads"), "new-guest");
});
