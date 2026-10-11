const assert = require("node:assert/strict");
const { test } = require("node:test");
const load = require("./load-ts");
const { readReportStream } = load(require("node:path").join(__dirname, "../src/lib/reportStream.ts"));
const event = data => `data: ${JSON.stringify(data)}\n\n`;
const artifact = { type: "report_complete", download_url: `/api/v1/report/download/${"a".repeat(32)}` };

test("artifact is published only after the terminal event including an unterminated last line", async () => {
    const events = [];
    await readReportStream(new Response(event({ type: "section_content", chunk: "结果完整。" }) + event(artifact) + 'data: {"type":"done"}'), value => events.push(value));
    assert.equal(events[0].chunk, "结果完整。");
    assert.equal(events[1].type, "report_complete");
    assert.equal(events[2].type, "done");
});
test("a lost stream cannot publish an artifact or succeed with a terminal event alone", async () => {
    for (const body of [event(artifact), event({ type: "done" })]) {
        const events = [];
        await assert.rejects(readReportStream(new Response(body), value => events.push(value)), /before completion/);
        assert.equal(events.length, 0);
    }
});
test("quota and provider errors stop a report even after partial sections", async () => {
    await assert.rejects(readReportStream(new Response(event({ type: "section_content", chunk: "Partial" }) + event({ type: "error", message: "Usage limit reached" }) + event({ type: "done" })), () => {}), /Usage limit/);
});
test("untrusted download URLs and non-JSON server failures are rejected", async () => {
    await assert.rejects(readReportStream(new Response(event({ ...artifact, download_url: "https://example.com/trap" })), () => {}), /valid download/);
    await assert.rejects(readReportStream(new Response("Private traceback", { status: 503 }), () => {}), /temporarily unavailable/);
});
