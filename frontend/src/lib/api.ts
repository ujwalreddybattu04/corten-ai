/** Same-origin client. JWTs stay in HttpOnly cookies. */
interface ApiOptions extends Omit<RequestInit, "body"> { body?: unknown; token?: string; }
export const SESSION_EXPIRED = "corten_session_expired";
let refreshInFlight: Promise<boolean> | null = null;
let sessionGeneration = 0;
export function invalidateSessionRequests() { sessionGeneration++; }
export class ApiRequestError extends Error {
    constructor(message: string, public status: number) { super(message); }
}
export function errorMessage(data: unknown): string {
    if (!data || typeof data !== "object") return "The request failed. Please try again.";
    const detail = (data as { detail?: unknown; message?: unknown }).detail ?? (data as { message?: unknown }).message;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map(item => typeof item?.msg === "string" ? item.msg.replace(/^Value error, /, "") : "Invalid input").join(". ");
    return "The request failed. Please try again.";
}
async function refreshSession(): Promise<boolean> {
    if (!refreshInFlight) {
        const generation = sessionGeneration;
        refreshInFlight = (async () => {
            const refresh = async () => {
                if (generation !== sessionGeneration) return false;
                const response = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}", cache: "no-store" });
                if (response.status === 401 && generation === sessionGeneration && typeof window !== "undefined") window.dispatchEvent(new Event(SESSION_EXPIRED));
                if (!response.ok && response.status !== 401) throw new ApiRequestError(errorMessage(await response.json().catch(() => null)), response.status);
                return response.ok && generation === sessionGeneration;
            };
            if (typeof navigator !== "undefined" && navigator.locks) {
                return navigator.locks.request("corten-refresh", async () => {
                    const check = await fetch("/api/v1/auth/me", { credentials: "same-origin", cache: "no-store" });
                    if (check.ok) return generation === sessionGeneration;
                    if (check.status !== 401) throw new ApiRequestError("Unable to verify your session. Please try again.", check.status);
                    return refresh();
                });
            }
            return refresh();
        })().finally(() => { refreshInFlight = null; });
    }
    return refreshInFlight;
}
async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
    const { body, token, ...init } = options;
    const generation = sessionGeneration;
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const send = () => fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store", body: body === undefined ? undefined : JSON.stringify(body) });
    let res = await send();
    const authMutation = /^\/api\/v1\/auth\/(login|register|refresh|logout)$/.test(path);
    if (res.status === 401 && !authMutation && !token && generation === sessionGeneration && await refreshSession()) {
        if (generation !== sessionGeneration) throw new ApiRequestError("Session changed. Please try again.", 401);
        res = await send();
    }
    if (!res.ok) throw new ApiRequestError(errorMessage(await res.json().catch(() => null)), res.status);
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
}
export const api = {
    get: <T>(path: string, opts?: ApiOptions) => request<T>(path, { ...opts, method: "GET" }),
    post: <T>(path: string, body?: unknown, opts?: ApiOptions) => request<T>(path, { ...opts, method: "POST", body }),
    put: <T>(path: string, body?: unknown, opts?: ApiOptions) => request<T>(path, { ...opts, method: "PUT", body }),
    patch: <T>(path: string, body?: unknown, opts?: ApiOptions) => request<T>(path, { ...opts, method: "PATCH", body }),
    delete: <T>(path: string, opts?: ApiOptions) => request<T>(path, { ...opts, method: "DELETE" }),
};
