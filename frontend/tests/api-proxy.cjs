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
const originalRenderUrl = process.env.RENDER_EXTERNAL_URL;
const originalAudience = process.env.BACKEND_IDENTITY_AUDIENCE;
delete process.env.BACKEND_IDENTITY_AUDIENCE;
after(() => {
  global.fetch = originalFetch;
  if (originalBackend === undefined) delete process.env.BACKEND_URL;
  else process.env.BACKEND_URL = originalBackend;
  if (originalRenderUrl === undefined) delete process.env.RENDER_EXTERNAL_URL;
  else process.env.RENDER_EXTERNAL_URL = originalRenderUrl;
  if (originalAudience === undefined) delete process.env.BACKEND_IDENTITY_AUDIENCE;
  else process.env.BACKEND_IDENTITY_AUDIENCE = originalAudience;
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

test("multipart interpolation uploads preserve Unicode CSV bytes and the generated boundary", async () => {
  const form = new FormData();
  const bytes = new TextEncoder().encode("year,中文採用率\r\n1,25%\r\n");
  form.append("file", new Blob([bytes], { type: "text/csv" }), "input.csv");
  const req = new Request("https://corten.example/api/v1/interpolation/preview?encoding=auto", { method: "POST", body: form });
  req.nextUrl = new URL(req.url);
  const boundary = req.headers.get("content-type");
  global.fetch = async (url, options) => {
    assert.equal(url, "https://backend.example/api/v1/interpolation/preview?encoding=auto");
    assert.equal(options.headers.get("content-type"), boundary);
    assert.ok(Buffer.from(options.body).includes(Buffer.from(bytes)));
    return Response.json({ columns: ["中文採用率"] });
  };
  process.env.BACKEND_URL = "https://backend.example";
  assert.equal((await api.POST(req, context(["interpolation", "preview"]))).status, 200);
});

test("interpolation upload limits reject declared and streamed oversized bodies before upstream fetch", async () => {
  let calls = 0;
  global.fetch = async () => { calls++; throw new Error("unexpected upload"); };
  const declared = new Request("https://corten.example/api/v1/interpolation/preview", { method: "POST", headers: { "content-length": "20971520" }, body: "small" });
  declared.nextUrl = new URL(declared.url);
  assert.equal((await api.POST(declared, context(["interpolation", "preview"]))).status, 413);
  const streamed = new Request(declared.url, { method: "POST", body: new Uint8Array(10 * 1024 * 1024 + 65537) });
  streamed.nextUrl = new URL(streamed.url);
  assert.equal((await api.POST(streamed, context(["interpolation", "preview"]))).status, 413);
  assert.equal(calls, 0);
});

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

test("Cloud Run service identity is cached and kept separate from the user's JWT", async () => {
  const audience = "https://corten-api-review.run.app";
  const oldBackend = process.env.BACKEND_URL;
  process.env.BACKEND_URL = audience; process.env.BACKEND_IDENTITY_AUDIENCE = audience;
  const token = `header.${Buffer.from(JSON.stringify({ aud: audience, exp: Math.floor(Date.now()/1000) + 3600 })).toString("base64url")}.signature`;
  let metadataCalls = 0, backendCalls = 0;
  global.fetch = async (url, options) => {
    if (url.startsWith("http://metadata.google.internal/")) {
      metadataCalls++; assert.equal(options.headers["Metadata-Flavor"], "Google");
      assert.equal(new URL(url).searchParams.get("audience"), audience);
      return new Response(token);
    }
    backendCalls++; assert.ok(url.startsWith(audience));
    assert.equal(options.headers.get("Authorization"), "Bearer test-token");
    assert.equal(options.headers.get("X-Serverless-Authorization"), `Bearer ${token}`);
    return Response.json({ status: "ready" });
  };
  try {
    const responses = await Promise.all([api.GET(request("GET"), context(["search","status"])), api.GET(request("GET"), context(["search","status"]))]);
    assert.ok(responses.every(r => r.ok)); assert.equal(metadataCalls, 1); assert.equal(backendCalls, 2);
    assert.ok((await api.GET(request("GET"), context(["search","status"]))).ok);
    assert.equal(metadataCalls, 1);
  } finally { process.env.BACKEND_URL = oldBackend; delete process.env.BACKEND_IDENTITY_AUDIENCE; }
});

test("invalid Cloud Run audience and metadata failures fail closed without leaking identity", async () => {
  const oldBackend = process.env.BACKEND_URL;
  for (const invalid of [true, false]) {
    process.env.BACKEND_URL = invalid ? "https://untrusted.example" : "https://failing-api.run.app";
    process.env.BACKEND_IDENTITY_AUDIENCE = process.env.BACKEND_URL;
    let calls = 0;
    global.fetch = async url => {
      calls++; assert.ok(url.startsWith("http://metadata.google.internal/"));
      return new Response("private identity failure", { status: 500 });
    };
    try {
      const response = await api.GET(request("GET"), context(["search","status"]));
      assert.equal(response.status, 502); assert.ok(!(await response.text()).includes("private"));
      assert.equal(calls, invalid ? 0 : 1);
    } finally { process.env.BACKEND_URL = oldBackend; delete process.env.BACKEND_IDENTITY_AUDIENCE; }
  }
});

const authRequest = (action, body = {}, cookies = "", origin = "https://corten.example") => {
  const req = new Request(`https://corten.example/api/v1/auth/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json", cookie: cookies, origin }, body: JSON.stringify(body),
  });
  req.nextUrl = new URL(req.url);
  return req;
};

test("login keeps JWTs out of JSON and creates secure HttpOnly session cookies", async () => {
  global.fetch = async (_url, options) => {
    assert.equal(JSON.parse(options.body).remember_me, undefined);
    return Response.json({ user: { id: "a" }, access_token: "access-jwt", refresh_token: "refresh-jwt" });
  };
  const response = await api.POST(authRequest("login", { email: "a@example.com", password: "password" }), context(["auth", "login"]));
  assert.deepEqual(await response.json(), { user: { id: "a" } });
  const cookies = response.headers.getSetCookie();
  assert.equal(cookies.length, 3);
  assert.ok(cookies.every(cookie => cookie.includes("HttpOnly") && cookie.includes("Secure") && cookie.includes("SameSite=Lax") && !cookie.includes("Max-Age")));
});

test("remember me sets persistent cookies and refresh retains that preference", async () => {
  global.fetch = async () => Response.json({ access_token: "new-access", refresh_token: "new-refresh" });
  let response = await api.POST(authRequest("login", { remember_me: true }), context(["auth", "login"]));
  assert.match(response.headers.getSetCookie()[1], /Max-Age=604800/);
  global.fetch = async (_url, options) => {
    assert.equal(JSON.parse(options.body).refresh_token, "saved-refresh");
    return Response.json({ access_token: "new-access", refresh_token: "new-refresh" });
  };
  response = await api.POST(authRequest("refresh", {}, "corten_refresh=saved-refresh; corten_remember=1"), context(["auth", "refresh"]));
  assert.match(response.headers.getSetCookie()[1], /Max-Age=604800/);
  assert.equal((await response.json()).refresh_token, undefined);
});

test("cookie sessions inject access credentials without forwarding cookies upstream", async () => {
  const req = new Request("https://corten.example/api/v1/auth/me", { headers: { cookie: "corten_access=private-access; unrelated=secret" } });
  req.nextUrl = new URL(req.url);
  global.fetch = async (_url, options) => {
    assert.equal(options.headers.get("authorization"), "Bearer private-access");
    assert.equal(options.headers.get("cookie"), null);
    return Response.json({ id: "a" });
  };
  assert.equal((await api.GET(req, context(["auth", "me"]))).status, 200);
});

test("cross-origin and origin-less cookie writes are rejected before reaching the backend", async () => {
  global.fetch = async () => assert.fail("Cross-origin authentication reached backend");
  for (const origin of ["https://evil.example", ""]) {
    const response = await api.POST(authRequest("logout", {}, "corten_refresh=token", origin), context(["auth", "logout"]));
    assert.equal(response.status, 403);
  }
});

test("failed logout clears access but retains HttpOnly refresh for a real revocation retry", async () => {
  global.fetch = async () => { throw new Error("connection failure"); };
  const response = await api.POST(authRequest("logout", {}, "corten_refresh=token"), context(["auth", "logout"]));
  assert.equal(response.status, 502);
  assert.ok(response.headers.getSetCookie().every(cookie => cookie.includes("Max-Age=0")));
  assert.ok(response.headers.getSetCookie().every(cookie => cookie.startsWith("corten_access=")));
  global.fetch = async (_url, options) => {
    assert.equal(JSON.parse(options.body).refresh_token, "token");
    return new Response(null, { status: 204 });
  };
  const retry = await api.POST(authRequest("logout", {}, "corten_refresh=token"), context(["auth", "logout"]));
  assert.equal(retry.status, 204);
  assert.ok(["corten_access", "corten_refresh", "corten_remember"].every(name => retry.headers.getSetCookie().some(cookie => cookie.startsWith(name + "=") && cookie.includes("Max-Age=0"))));
});

test("expired refresh clears cookies and does not expose credentials", async () => {
  global.fetch = async () => Response.json({ detail: "Revoked" }, { status: 401 });
  const response = await api.POST(authRequest("refresh", {}, "corten_refresh=token"), context(["auth", "refresh"]));
  assert.equal(response.status, 401);
  assert.equal(response.headers.getSetCookie().length, 3);
  assert.ok(response.headers.getSetCookie().every(cookie => cookie.includes("Max-Age=0")));
});

test("guests restore immediately without waking backend; cookie sessions are verified by backend", async () => {
  let calls = 0;
  global.fetch = async (url, options) => {
    calls++;
    assert.match(url, /\/auth\/me$/);
    assert.equal(options.headers.get("authorization"), "Bearer saved-access");
    return Response.json({ id: "verified-user" });
  };
  let req = new Request("https://corten.example/api/v1/auth/session");
  req.nextUrl = new URL(req.url);
  assert.equal(await (await api.GET(req, context(["auth", "session"]))).json(), null);
  assert.equal(calls, 0);
  req = new Request(req.url, { headers: { cookie: "corten_access=saved-access" } });
  req.nextUrl = new URL(req.url);
  assert.equal((await (await api.GET(req, context(["auth", "session"]))).json()).id, "verified-user");
  assert.equal(calls, 1);
});

test("Render public HTTPS origin permits browser sign-in and secures cookies behind internal HTTP", async () => {
  process.env.RENDER_EXTERNAL_URL = "https://corten.example";
  global.fetch = async () => Response.json({ user: { id: "a" }, access_token: "access", refresh_token: "refresh" });
  const req = new Request("http://internal-container:10000/api/v1/auth/login", {
    method: "POST", headers: { Origin: "https://corten.example", "Content-Type": "application/json" }, body: "{}",
  });
  req.nextUrl = new URL(req.url);
  const response = await api.POST(req, context(["auth", "login"]));
  assert.equal(response.status, 200);
  assert.ok(response.headers.getSetCookie().every(cookie => cookie.includes("Secure")));
  const crossSite = authRequest("login", {}, "", "https://attacker.example");
  assert.equal((await api.POST(crossSite, context(["auth", "login"]))).status, 403);
  if (originalRenderUrl === undefined) delete process.env.RENDER_EXTERNAL_URL;
  else process.env.RENDER_EXTERNAL_URL = originalRenderUrl;
});
