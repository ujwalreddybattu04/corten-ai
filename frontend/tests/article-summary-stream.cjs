const test = require("node:test");
const assert = require("node:assert/strict");
const loadTs = require("./load-ts");
const path = require("node:path");
const { readArticleSummary } = loadTs(path.join(__dirname, "../src/lib/articleSummaryStream.ts"));
const encode = event => `data: ${JSON.stringify(event)}\n\n`;

test("a fast response preserves all text including the final sentence", async () => {
    const text = "The report explains the outcome. ".repeat(80) + "This is the complete final sentence. [1]";
    const result = await readArticleSummary(new Response(
        encode({ type: "token", content: text }) + encode({ type: "done" })
    ), () => {});
    assert.equal(result, text);
});

test("the last SSE record is read even without a trailing newline", async () => {
    const result = await readArticleSummary(new Response(
        encode({ type: "token", content: "A complete summary." }) + 'data: {"type":"done"}'
    ), () => {});
    assert.equal(result, "A complete summary.");
});

test("split UTF-8 characters and SSE records preserve exact text", async () => {
    const text = "测试已经完成。 A complete result. [1]";
    const bytes = new TextEncoder().encode(encode({ type: "token", content: text }) + encode({ type: "done" }));
    const stream = new ReadableStream({ start(controller) {
        for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
        controller.close();
    } });
    assert.equal(await readArticleSummary(new Response(stream), () => {}), text);
});

test("an explicit backend error is never swallowed as a successful completion", async () => {
    const body = encode({ type: "token", content: "A partial draft" }) +
        encode({ type: "error", message: "The summary could not be completed. Please retry." }) + encode({ type: "done" });
    await assert.rejects(readArticleSummary(new Response(body), () => {}), /could not be completed/);
});

test("an interrupted stream or empty completion is rejected", async () => {
    for (const body of [encode({ type: "token", content: "A partial draft" }), encode({ type: "done" })]) {
        await assert.rejects(readArticleSummary(new Response(body), () => {}), /before completion/);
    }
});

test("non-JSON service outages give a retryable message without exposing the body", async () => {
    await assert.rejects(readArticleSummary(new Response("private proxy details", { status: 503 }), () => {}),
        error => error.message.includes("temporarily unavailable") && !error.message.includes("private proxy details"));
});
