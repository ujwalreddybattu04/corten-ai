const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");
const Module = require("node:module");
const path = require("node:path");

function setup(threads = []) {
    const source = path.join(__dirname, "../src/lib/threadTitles.ts");
    const instance = new Module(source, module);
    instance._compile(ts.transpileModule(fs.readFileSync(source, "utf8"), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText, source);
    const values = new Map([["corten_threads", JSON.stringify(threads)]]);
    const session = new Map();
    global.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
    global.sessionStorage = { getItem: key => session.get(key) || null };
    global.window = { location: { hostname: "localhost" }, dispatchEvent() {} };
    return { ...instance.exports, read: () => JSON.parse(values.get("corten_threads")),
        save: threads => values.set("corten_threads", JSON.stringify(threads)), session };
}

const thread = (id = "a", query = "write a python code") => ({ id, query, title: query, answer: "Python example", history: [], updatedAt: 100 });
const reply = (title, source = "generated") => ({ ok: true, json: async () => ({ title, source }) });
async function until(condition) {
    for (let i = 0; i < 100; i++) {
        if (condition()) return;
        await new Promise(resolve => setTimeout(resolve, 2));
    }
    assert.fail("Title update did not complete");
}

test("instant title responses are saved against an already persisted exact ID", async () => {
    const api = setup([thread()]);
    let calls = 0;
    global.fetch = async (_url, options) => {
        assert.equal(api.read()[0].id, "a");
        assert.equal(JSON.parse(options.body).query, "write a python code");
        calls++;
        return reply("Python Coding Help");
    };
    api.refreshThreadTitles();
    api.scheduleThreadTitle("a");
    await until(() => api.read()[0].titleSource === "generated");
    assert.equal(api.read()[0].title, "Python Coding Help");
    api.refreshThreadTitles();
    assert.equal(calls, 1, "remounts and update events must not duplicate generation");
});

test("identical prompts never rename the wrong thread and requests run serially", async () => {
    const api = setup([thread("a"), thread("b")]);
    let calls = 0;
    let active = 0;
    global.fetch = async () => {
        assert.equal(++active, 1);
        const title = ++calls === 1 ? "Python Function Examples" : "Python Script Basics";
        await new Promise(resolve => setTimeout(resolve, 5));
        active--;
        return reply(title);
    };
    api.refreshThreadTitles();
    await until(() => api.read().every(t => t.titleSource === "generated"));
    assert.deepEqual(api.read().map(t => t.title), ["Python Function Examples", "Python Script Basics"]);
    assert.equal(calls, 2);
});

test("a delayed title preserves a manual rename and unrelated new content", async () => {
    const api = setup([thread()]);
    let release;
    global.fetch = () => new Promise(resolve => { release = resolve; });
    api.refreshThreadTitles();
    const current = api.read()[0];
    api.save([{ ...current, title: "Team Planning", titleSource: "manual", answer: "Newer answer" }]);
    release(reply("Python Coding Help"));
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(api.read()[0].title, "Team Planning");
    assert.equal(api.read()[0].answer, "Newer answer");
});

test("a deleted thread is never recreated by a late title response", async () => {
    const api = setup([thread()]);
    let release;
    global.fetch = () => new Promise(resolve => { release = resolve; });
    api.refreshThreadTitles();
    api.save([]);
    release(reply("Python Coding Help"));
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.deepEqual(api.read(), []);
});

test("greetings use a provisional heading then name the first substantive topic", async () => {
    const api = setup([thread("a", "hi corten")]);
    const queries = [];
    global.fetch = async (_url, options) => { queries.push(JSON.parse(options.body).query); return reply("Python Coding Help"); };
    api.refreshThreadTitles();
    assert.equal(api.read()[0].title, "New Conversation");
    assert.equal(queries.length, 0);
    api.save([api.prepareThreadTitle({ ...api.read()[0], query: "write a python code", history: [{ query: "hi corten", answer: "Hello" }] })]);
    api.scheduleThreadTitle("a");
    await until(() => api.read()[0].titleSource === "generated");
    assert.deepEqual(queries, ["write a python code"]);
});

test("old prompt headings are repaired while legacy custom titles remain intact", () => {
    const api = setup();
    assert.equal(api.prepareThreadTitle(thread()).title, "Python Coding");
    const custom = api.prepareThreadTitle({ ...thread(), title: "Sprint Planning" });
    assert.equal(custom.title, "Sprint Planning");
    assert.equal(custom.titleSource, "manual");
    const followup = api.prepareThreadTitle({ ...thread(), query: "What's my previous question?", history: [{ query: "write a python code", answer: "Example" }] });
    assert.equal(followup.title, "Python Coding");
    assert.equal(followup.titleTopic, "write a python code");
});

test("failed or malformed title output retains a topic heading with retry backoff", async () => {
    for (const response of [() => Promise.reject(new Error("offline")), () => Promise.resolve({ ok: false }),
        () => Promise.resolve(reply("write a python code")), () => Promise.resolve(reply("# Heading\nAn answer")),
        () => Promise.resolve(reply("Python Coding", "fallback"))]) {
        const api = setup([thread()]);
        let calls = 0;
        global.fetch = (...args) => { calls++; return response(...args); };
        api.refreshThreadTitles();
        await until(() => api.read()[0].titleSource === "fallback");
        assert.equal(api.read()[0].title, "Python Coding");
        assert.ok(api.read()[0].titleRetryAt > Date.now());
        api.refreshThreadTitles();
        assert.equal(calls, 1);
    }
});

test("private mode neither sends title requests nor mutates stored history", async () => {
    const api = setup([thread()]);
    api.session.set("corten_private_mode", "true");
    global.fetch = () => assert.fail("Private title request");
    api.refreshThreadTitles();
    api.scheduleThreadTitle("a");
    assert.equal(api.read()[0].title, "write a python code");
});

test("entering private mode while a title is pending prevents the response write", async () => {
    const api = setup([thread()]);
    let release;
    global.fetch = () => new Promise(resolve => { release = resolve; });
    api.refreshThreadTitles();
    api.session.set("corten_private_mode", "true");
    release(reply("Python Coding Help"));
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(api.read()[0].title, "Python Coding");
});
