const assert = require("node:assert/strict");
const { test } = require("node:test");
const path = require("node:path");
const load = require("./load-ts");
const source = path.join(__dirname, "../src/services/interpolationService.ts");
const input = () => new File(["year,中文\n1,25%"], "input.csv", { type: "text/csv" });

test("preview recovers from a startup HTML 503 with the same file and encoding", async (t) => {
    const { interpolationService } = load(source);
    const file = input(), delays = [];
    let calls = 0;
    const timer = global.setTimeout;
    t.mock.method(global, "setTimeout", (callback, delay) => { delays.push(delay); return timer(callback, 0); });
    t.mock.method(global, "fetch", async (url, options) => {
        calls++;
        assert.ok(url.includes("preview?encoding=utf-8-sig"));
        assert.equal(options.body.get("file"), file);
        assert.equal(await options.body.get("file").text(), "year,中文\n1,25%");
        return calls === 1 ? new Response("Starting service", { status: 503 }) : Response.json({ columns: ["中文"] });
    });
    assert.deepEqual(await interpolationService.preview(file, "utf-8-sig", new AbortController().signal), { columns: ["中文"] });
    assert.equal(calls, 2);
    assert.deepEqual(delays, [2000]);
});

test("persistent gateway errors stop after three attempts with a clear recoverable error", async (t) => {
    const { interpolationService } = load(source);
    let calls = 0;
    const delays = [], timer = global.setTimeout;
    t.mock.method(global, "setTimeout", (callback, delay) => { delays.push(delay); return timer(callback, 0); });
    t.mock.method(global, "fetch", async () => { calls++; return new Response("Gateway unavailable", { status: 502 }); });
    await assert.rejects(interpolationService.preview(input(), "auto", new AbortController().signal), error => error.status === 502 && error.message.includes("Your file is still selected"));
    assert.equal(calls, 3);
    assert.deepEqual(delays, [2000, 4000]);
});

test("replacing an upload cancels its retry delay and prevents another request", async (t) => {
    const { interpolationService } = load(source);
    const controller = new AbortController(), timer = global.setTimeout;
    let calls = 0, notify;
    const delayStarted = new Promise(resolve => { notify = resolve; });
    t.mock.method(global, "setTimeout", (callback, delay) => { notify(); return timer(callback, delay); });
    t.mock.method(global, "fetch", async () => { calls++; return new Response("Unavailable", { status: 504 }); });
    const preview = interpolationService.preview(input(), "auto", controller.signal);
    const rejected = assert.rejects(preview, error => error.name === "AbortError");
    await delayStarted;
    controller.abort();
    await rejected;
    await new Promise(resolve => timer(resolve, 10));
    assert.equal(calls, 1);
});

test("invalid uploads and calculations are not automatically retried", async (t) => {
    const { interpolationService } = load(source);
    let calls = 0;
    t.mock.method(global, "fetch", async () => { calls++; return Response.json({ detail: "Years must be consecutive" }, { status: 400 }); });
    await assert.rejects(interpolationService.preview(input(), "auto", new AbortController().signal), /Years must be consecutive/);
    assert.equal(calls, 1);
    calls = 0;
    t.mock.method(global, "fetch", async () => { calls++; return Response.json({ detail: "Calculation service is busy" }, { status: 503 }); });
    await assert.rejects(interpolationService.calculate(input(), "auto", "average", new AbortController().signal), error => error.status === 503);
    assert.equal(calls, 1);
});
