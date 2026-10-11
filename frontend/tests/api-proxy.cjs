const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const ts = require("typescript");
const Module = require("node:module");
const path = require("node:path");
const source = path.join(__dirname, "../src/app/api/v1/[[...path]]/route.ts");
const compiled = ts.transpileModule(fs.readFileSync(source, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const instance = new Module(source, module);
instance._compile(compiled, source);
const api = instance.exports;
const originalFetch = global.fetch;
const originalBackend = process.env.BACKEND_URL;
after(() => {
  global.fetch = originalFetch;
  if (originalBackend === undefined) delete process.env.BACKEND_URL;
  else process.env.BACKEND_URL = originalBackend;
});
const context = (parts) => ({ params: Promise.resolve({ path: parts }) });
const request = (method, query = "", body) => {
  const req = new Request("https://corten.example/api/v1/search" + query, {
    method,
    headers: { Authorization: "Bearer test-token", "Content-Type": "application/json" },
    body,
  });
  req.nextUrl = new URL(req.url);
  return req;
};

test("proxy forwards auth, query filters and a binary PDF download", async () => {
  process.env.BACKEND_URL = "https://backend.example/";
  global.fetch = async (url, options) => {
    assert.equal(url, "https://backend.example/api/v1/report/download/sample?days=7");
    assert.equal(options.headers.get("authorization"), "Bearer test-token");
    assert.equal(options.cache, "no-store");
    return new Response(new Uint8Array([37, 80, 68, 70]), {
      headers: { "Content-Type": "application/pdf", "Content-Disposition": "attachment; filename=report.pdf" },
    });
  };
  const res = await api.GET(request("GET", "?days=7"), context(["report", "download", "sample"]));
  assert.equal(res.headers.get("content-type"), "application/pdf");
  assert.match(res.headers.get("content-disposition"), /report.pdf/);
  assert.equal(await res.text(), "%PDF");
});

test("proxy forwards write methods and preserves empty deletion response", async () => {
  global.fetch = async (_url, options) => {
    assert.equal(options.method, "DELETE");
    return new Response(null, { status: 204 });
  };
  const res = await api.DELETE(request("DELETE"), context(["threads", "sample"]));
  assert.equal(res.status, 204);
  assert.equal(await res.text(), "");
});

test("proxy preserves streamed answers and error status/body", async () => {
  global.fetch = async (_url, options) => {
    assert.equal(Buffer.from(options.body).toString(), '{"query":"hi"}');
    return new Response("data: hello\n\n", { headers: { "Content-Type": "text/event-stream" } });
  };
  let res = await api.POST(request("POST", "", '{"query":"hi"}'), context(["search"]));
  assert.match(res.headers.get("content-type"), /text\/event-stream/);
  assert.equal(await res.text(), "data: hello\n\n");
  global.fetch = async () => Response.json({ detail: "Not authorized" }, { status: 401 });
  res = await api.GET(request("GET"), context(["users", "me"]));
  assert.equal(res.status, 401);
  assert.deepEqual(await res.json(), { detail: "Not authorized" });
});

test("proxy blocks path traversal and hides internal connection errors", async () => {
  global.fetch = async () => { throw new Error("private-hostname-and-sensitive-details"); };
  let res = await api.GET(request("GET"), context(["..", "health"]));
  assert.equal(res.status, 400);
  res = await api.GET(request("GET"), context(["pharma", "updates"]));
  assert.equal(res.status, 502);
  assert.doesNotMatch(await res.text(), /private-hostname/);
});
