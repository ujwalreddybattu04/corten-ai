/**
 * API client — thin wrapper around fetch that handles
 * base URL, Authorization header injection, and error normalization.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface ApiOptions extends Omit<RequestInit, "body"> {
    body?: unknown;
    token?: string;
}

interface ApiError {
    message: string;
    status: number;
}

export class ApiRequestError extends Error {
    status: number;
    constructor(message: string, status: number) {
        super(message);
        this.status = status;
    }
}

async function request<T>(path: string, options: ApiOptions = {}): Promise<T> {
    const { body, token, ...init } = options;

    const headers: Record<string, string> = {
        "Content-Type": "application/json",
    };

    // Inject stored token if available
    const storedToken = token || (typeof window !== "undefined"
        ? localStorage.getItem("corten_access_token")
        : null);
    if (storedToken) {
        headers["Authorization"] = `Bearer ${storedToken}`;
    }

    const res = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: { ...headers, ...((init.headers as Record<string, string>) || {}) },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
        let message = "An error occurred";
        try {
            const data = await res.json();
            message = data?.detail || data?.message || message;
        } catch { /* ignore parse error */ }
        throw new ApiRequestError(message, res.status);
    }

    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
}

export const api = {
    get:    <T>(path: string, opts?: ApiOptions) => request<T>(path, { ...opts, method: "GET" }),
    post:   <T>(path: string, body?: unknown, opts?: ApiOptions) => request<T>(path, { ...opts, method: "POST", body }),
    put:    <T>(path: string, body?: unknown, opts?: ApiOptions) => request<T>(path, { ...opts, method: "PUT", body }),
    patch:  <T>(path: string, body?: unknown, opts?: ApiOptions) => request<T>(path, { ...opts, method: "PATCH", body }),
    delete: <T>(path: string, opts?: ApiOptions) => request<T>(path, { ...opts, method: "DELETE" }),
};
