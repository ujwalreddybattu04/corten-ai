const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");
const Module = require("node:module");
const path = require("node:path");
const source = path.join(__dirname, "../src/lib/conversation.ts");
const instance = new Module(source, module);
instance._compile(ts.transpileModule(fs.readFileSync(source, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText, source);
const { conversationMessages } = instance.exports;

test("follow-ups send questions and answers in their original chronological roles", () => {
  const history = [{ query: "Project Meridian is in India", answer: "Noted" },
    { query: "Correction: Japan", answer: "Updated" }];
  assert.deepEqual(conversationMessages(history), [
    { role: "user", content: history[0].query }, { role: "assistant", content: "Noted" },
    { role: "user", content: history[1].query }, { role: "assistant", content: "Updated" },
  ]);
  assert.deepEqual(conversationMessages([]), []);
});

test("long threads stay within API bounds and preserve the latest correction and message tail", () => {
  const history = Array.from({ length: 80 }, (_, i) => ({ query: "Question " + i, answer: "Answer " + i }));
  history[79].query = "Latest correction: " + "x".repeat(12000) + " Country is Japan.";
  const messages = conversationMessages(history);
  assert.equal(messages.length, 120);
  assert.equal(messages[0].content, "Question 20");
  assert.ok(messages.at(-2).content.startsWith("Latest correction"));
  assert.ok(messages.at(-2).content.endsWith("Country is Japan."));
  assert.equal(messages.at(-2).content.length, 6000);
  assert.equal(history.length, 80);
  assert.ok(history[79].query.length > 6000);
});
