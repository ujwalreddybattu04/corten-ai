import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ path?: string[] }> };

async function proxy(request: NextRequest, { params }: RouteContext) {
    const { path = [] } = await params;
    if (path.some(part => part === "." || part === ".." || /[\\/]/.test(part))) {
        return Response.json({ detail: "Invalid API path" }, { status: 400 });
    }
    const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    const target = `${backend}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
    const headers = new Headers();
    for (const name of ["authorization", "content-type", "accept"]) {
        const value = request.headers.get(name);
        if (value) headers.set(name, value);
    }
    try {
        const upstream = await fetch(target, {
            method: request.method,
            headers,
            body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
            cache: "no-store",
            redirect: "manual",
            signal: AbortSignal.timeout(300_000),
        });
        const responseHeaders = new Headers({ "Cache-Control": "no-store" });
        for (const name of ["content-type", "content-disposition", "retry-after"]) {
            const value = upstream.headers.get(name);
            if (value) responseHeaders.set(name, value);
        }
        // Preserve JSON, PDF downloads, empty responses, errors and streamed answers.
        return new Response(upstream.body, {
            status: upstream.status,
            headers: responseHeaders,
        });
    } catch {
        return Response.json({ detail: "Backend unavailable. Please try again shortly." }, { status: 502 });
    }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as HEAD };
