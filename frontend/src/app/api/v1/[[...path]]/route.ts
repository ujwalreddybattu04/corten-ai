import type { NextRequest } from "next/server";
import { POST as executeCode } from "../../execute/route";

export const dynamic = "force-dynamic";
type RouteContext = { params: Promise<{ path?: string[] }> };
const ACCESS = "corten_access";
const REFRESH = "corten_refresh";
const PERSIST = "corten_remember";
let identity: { audience: string; token: string; expires: number } | null = null;
let identityPending: { audience: string; promise: Promise<string> } | null = null;
async function cloudRunIdentity(backend: string): Promise<string | null> {
    const audience = process.env.BACKEND_IDENTITY_AUDIENCE;
    if (!audience) return null;
    const target = new URL(backend);
    if (target.protocol !== "https:" || !target.hostname.endsWith(".run.app") || target.username || target.password
        || target.origin !== audience || target.pathname !== "/" || target.search || target.hash) throw new Error("Invalid Cloud Run backend configuration");
    if (identity?.audience === audience && identity.expires > Date.now() + 60_000) return identity.token;
    if (identityPending?.audience === audience) return identityPending.promise;
    const promise = (async () => {
        const response = await fetch(`http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${encodeURIComponent(audience)}&format=full`, {
            headers: { "Metadata-Flavor": "Google" }, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error("Cloud Run service identity unavailable");
        const token = await response.text();
        if (token.length > 16_384 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token)) throw new Error("Invalid service identity");
        const claims = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString());
        if (claims.aud !== audience || typeof claims.exp !== "number" || !Number.isFinite(claims.exp) || claims.exp * 1000 <= Date.now() + 60_000) throw new Error("Expired service identity");
        identity = { audience, token, expires: claims.exp * 1000 };
        return token;
    })();
    identityPending = { audience, promise };
    try { return await promise; }
    finally { if (identityPending?.promise === promise) identityPending = null; }
}
// Render's internal request URL can be HTTP even when the public site uses HTTPS.
function publicOrigin(request: Request) {
    return new URL(process.env.APP_ORIGIN || process.env.RENDER_EXTERNAL_URL || request.url).origin;
}

function cookie(request: Request, name: string) {
    const entry = (request.headers.get("cookie") || "").split(";").find(part => part.trim().startsWith(name + "="));
    try {
        const value = entry ? decodeURIComponent(entry.trim().slice(name.length + 1)) : "";
        return /^[A-Za-z0-9_.-]{1,4096}$/.test(value) ? value : "";
    } catch { return ""; }
}
function setCookie(headers: Headers, request: Request, name: string, value: string, maxAge?: number) {
    headers.append("Set-Cookie", `${name}=${encodeURIComponent(value)}; Path=/api/v1; HttpOnly; SameSite=Lax${publicOrigin(request).startsWith("https:") ? "; Secure" : ""}${maxAge === undefined ? "" : `; Max-Age=${maxAge}`}`);
}
function clearSession(headers: Headers, request: Request) {
    for (const name of [ACCESS, REFRESH, PERSIST]) setCookie(headers, request, name, "", 0);
}
async function proxy(request: NextRequest, { params }: RouteContext) {
    const { path = [] } = await params;
    if (path.some(part => part === "." || part === ".." || /[\\/]/.test(part))) {
        return Response.json({ detail: "Invalid API path" }, { status: 400 });
    }
    const action = path.length === 2 && path[0] === "auth" ? path[1] : "";
    const mutation = !["GET", "HEAD"].includes(request.method);
    const origin = request.headers.get("origin");
    const site = request.headers.get("sec-fetch-site");
    if (mutation && ((origin && origin !== publicOrigin(request)) || site === "cross-site" ||
        (!origin && !request.headers.has("authorization") && (action || cookie(request, ACCESS) || cookie(request, REFRESH))))) {
        return Response.json({ detail: "Request origin is not allowed" }, { status: 403 });
    }
    const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    if (path.length === 1 && path[0] === "execute" && request.method === "POST") return executeCode(request);
    const session = action === "session" && request.method === "GET";
    if (session && !cookie(request, ACCESS) && !cookie(request, REFRESH) && !request.headers.has("authorization")) {
        return Response.json(null, { headers: { "Cache-Control": "no-store", "Vary": "Cookie, Authorization" } });
    }
    const target = `${backend}/api/v1/${(session ? ["auth", "me"] : path).map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
    const headers = new Headers();
    const viewerIp = request.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim();
    if (viewerIp && /^[0-9a-fA-F:.]{3,64}$/.test(viewerIp)) headers.set("X-Corten-Client-IP", viewerIp);
    for (const name of ["authorization", "content-type", "accept"]) {
        const value = request.headers.get(name);
        if (value) headers.set(name, value);
    }
    const access = cookie(request, ACCESS);
    if (!headers.has("authorization") && access) headers.set("authorization", `Bearer ${access}`);
    if (!headers.has("authorization") && cookie(request, REFRESH)) headers.set("authorization", "Bearer expired-session");
    const responseHeaders = new Headers({ "Cache-Control": "no-store", "Vary": "Cookie, Authorization" });
    const logout = action === "logout" && request.method === "POST";
    // Keep only the HttpOnly refresh credential if revocation fails, so retry can
    // actually revoke the server session. The client hides private views meanwhile.
    if (logout) setCookie(responseHeaders, request, ACCESS, "", 0);
    try {
        const serviceToken = await cloudRunIdentity(backend);
        // Cloud Run IAM and the application's user JWT have separate headers.
        // Never forward a browser-supplied service identity header.
        if (serviceToken) headers.set("X-Serverless-Authorization", `Bearer ${serviceToken}`);
        let body: BodyInit | undefined;
        const spaceUpload = (path.length === 3 && path[0] === "spaces" && path[2] === "files") || (path.length === 1 && path[0] === "attachments");
        if (mutation && (path[0] === "interpolation" || spaceUpload)) {
            const limit = (spaceUpload ? 25 : 10) * 1024 * 1024 + 64 * 1024;
            const tooLarge = () => Response.json({ detail: spaceUpload ? "Files must be no larger than 25 MB." : "CSV files must be no larger than 10 MB." }, { status: 413, headers: responseHeaders });
            if (Number(request.headers.get("content-length")) > limit) return tooLarge();
            const reader = request.body?.getReader();
            if (reader) {
                const parts: Uint8Array[] = [];
                let size = 0;
                while (true) {
                    const part = await reader.read();
                    if (part.done) break;
                    size += part.value.byteLength;
                    if (size > limit) { await reader.cancel(); return tooLarge(); }
                    parts.push(part.value);
                }
                const bytes = new Uint8Array(size);
                let offset = 0;
                for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
                body = bytes;
            }
        } else if (mutation) body = await request.arrayBuffer();
        let remember = cookie(request, PERSIST) === "1";
        if (mutation && ["register", "login", "refresh", "logout"].includes(action)) {
            let data: Record<string, unknown>;
            try { data = JSON.parse(Buffer.from(body as ArrayBuffer).toString() || "{}"); }
            catch { return Response.json({ detail: "Invalid JSON request" }, { status: 400, headers: responseHeaders }); }
            if (!data || Array.isArray(data) || typeof data !== "object") return Response.json({ detail: "Invalid request" }, { status: 400, headers: responseHeaders });
            if (["register", "login"].includes(action)) {
                remember = data.remember_me === true;
                delete data.remember_me;
            } else {
                const refresh = cookie(request, REFRESH);
                if (refresh) data.refresh_token = refresh;
                if (logout && !data.refresh_token) {
                    clearSession(responseHeaders, request);
                    return new Response(null, { status: 204, headers: responseHeaders });
                }
                if (!data.refresh_token) {
                    clearSession(responseHeaders, request);
                    return Response.json({ detail: "No active session" }, { status: 401, headers: responseHeaders });
                }
            }
            body = JSON.stringify(data);
            headers.set("content-type", "application/json");
        }
        const upstream = await fetch(target, {
            method: request.method, headers, body, cache: "no-store", redirect: "manual",
            signal: AbortSignal.timeout(path.join("/") === "search/status" ? 10_000 : action ? 30_000 : 300_000),
        });
        for (const name of ["content-type", "content-disposition", "retry-after"]) {
            const value = upstream.headers.get(name);
            if (value) responseHeaders.set(name, value);
        }
        if (mutation && ["register", "login", "refresh"].includes(action) && upstream.ok) {
            const data = await upstream.json();
            if (typeof data.access_token !== "string" || typeof data.refresh_token !== "string") throw new Error("Invalid token response");
            setCookie(responseHeaders, request, ACCESS, data.access_token, remember ? 1800 : undefined);
            setCookie(responseHeaders, request, REFRESH, data.refresh_token, remember ? 604800 : undefined);
            setCookie(responseHeaders, request, PERSIST, remember ? "1" : "0", remember ? 604800 : undefined);
            delete data.access_token;
            delete data.refresh_token;
            return Response.json(data, { status: upstream.status, headers: responseHeaders });
        }
        if (action === "refresh" && upstream.status === 401) clearSession(responseHeaders, request);
        if (logout && upstream.ok) clearSession(responseHeaders, request);
        if (action === "reset-password" && upstream.ok) clearSession(responseHeaders, request);
        return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
    } catch {
        return Response.json({ detail: "Backend unavailable. Please try again shortly." }, { status: 502, headers: responseHeaders });
    }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as HEAD };
