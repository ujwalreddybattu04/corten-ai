const { test } = require("node:test");
const assert = require("node:assert/strict");
const loadTs = require("./load-ts");
const { openSearchStream } = loadTs("src/lib/searchConnection.ts");
const request = { apiBase: "", query: "Explain forecasting", focus: "all", messages: [{ role: "user", content: "Earlier context" }] };
const status = () => Response.json({ status: "ready" });
const stream = () => new Response('data: {"type":"token","content":"A complete answer."}\n\ndata: {"type":"done"}\n\n', { headers: { "Content-Type": "text/event-stream" } });
test("startup errors retry the inexpensive status GET before sending exactly one generation", async () => {
    const calls = [], notices = []; let checks = 0;
    const response = await openSearchStream(request, new AbortController().signal, x => notices.push(x), {
        budgetMs: 2000, delayMs: 1, fetcher: async (url, options) => {
            calls.push({ url, ...options });
            if (url.endsWith("/status")) return ++checks < 3 ? new Response("", { status: 502 }) : status();
            assert.equal(checks, 3);
            assert.deepEqual(JSON.parse(options.body), { query: request.query, focus_mode: "all", messages: request.messages });
            return stream();
        },
    });
    assert.equal(calls.filter(x => x.method === "POST").length, 1);
    assert.equal(calls.filter(x => x.url.endsWith("/status")).length, 3);
    assert.ok(notices.some(x => x.includes("may be starting")));
    assert.match(await response.text(), /complete answer/);
});
test("failed generation POST is never automatically duplicated", async () => {
    let posts = 0;
    await assert.rejects(openSearchStream(request, new AbortController().signal, () => {}, {
        fetcher: async (_url, options) => options.method === "POST" ? (posts++, new Response("private gateway details", { status: 502 })) : status(),
    }), error => error.message.includes("temporarily unavailable") && !error.message.includes("private"));
    assert.equal(posts, 1);
});
test("cancellation while waiting never submits the question", async () => {
    const controller = new AbortController(); let posts = 0;
    await assert.rejects(openSearchStream(request, controller.signal, text => {
        if (text.includes("may be starting")) controller.abort();
    }, {
        fetcher: async (_url, options) => { if (options.method === "POST") posts++; return new Response("", { status: 503 }); },
    }));
    assert.equal(posts, 0);
});
test("Retry-After beyond the budget does not submit or hammer the backend", async () => {
    let calls = 0;
    await assert.rejects(openSearchStream(request, new AbortController().signal, () => {}, {
        budgetMs: 50, fetcher: async () => { calls++; return new Response("", { status: 503, headers: { "Retry-After": "30" } }); },
    }), /temporarily unavailable/);
    assert.equal(calls, 1);
});
test("a hosting loading page is retried until the actual JSON status is ready", async () => {
    let checks = 0, posts = 0;
    await openSearchStream(request, new AbortController().signal, () => {}, {
        delayMs: 1, fetcher: async (_url, options) => {
            if (options.method === "POST") { posts++; return stream(); }
            return ++checks === 1 ? new Response("<html>starting</html>") : status();
        },
    });
    assert.equal(checks, 2); assert.equal(posts, 1);
});
test("unrecognized status cannot cause a generation and waiting has a deadline", async () => {
    let posts = 0;
    await assert.rejects(openSearchStream(request, new AbortController().signal, () => {}, {
        budgetMs: 25, delayMs: 5, fetcher: async (_url, options) => { if (options.method === "POST") posts++; return Response.json({ status: "starting" }); },
    }), /temporarily unavailable/);
    assert.equal(posts, 0);
});
test("non-transient status failures stop without a generation", async () => {
    let calls = 0;
    await assert.rejects(openSearchStream(request, new AbortController().signal, () => {}, {
        fetcher: async () => { calls++; return new Response("", { status: 404 }); },
    })); assert.equal(calls, 1);
});
test("a network interruption during POST gives a retry message without resubmitting", async () => {
    let posts = 0;
    await assert.rejects(openSearchStream(request, new AbortController().signal, () => {}, {
        fetcher: async (_url, options) => { if (options.method !== "POST") return status(); posts++; throw new TypeError("sensitive upstream host"); },
    }), /Your question is still here/);
    assert.equal(posts, 1);
});

test("pharma generation sends a canonical record reference once and never mixes Space fields", async () => {
    const pharma = { record_id: "trial:NCT12345678", record_fingerprint: "[]", topic: "oncology", days: 30, kind: "brief" };
    let posts = 0;
    await openSearchStream({ ...request, pharma, mode: "pro" }, new AbortController().signal, () => {}, {
        fetcher: async (url, options) => {
            if (options.method !== "POST") return status();
            posts++; assert.equal(url, "/api/v1/pharma/analysis/stream");
            assert.deepEqual(JSON.parse(options.body), { query: request.query, messages: request.messages, ...pharma, mode: "pro" });
            return stream();
        },
    });
    assert.equal(posts, 1);
});

test("a changed pharma snapshot provides a recovery path without repeating generation", async () => {
    let posts = 0;
    await assert.rejects(openSearchStream({ ...request, pharma: {} }, new AbortController().signal, () => {}, {
        fetcher: async (_url, options) => options.method === "POST"
            ? (posts++, Response.json({ detail: "This source record has changed. Reopen it." }, { status: 409 })) : status(),
    }), /source record has changed/);
    assert.equal(posts, 1);
});
