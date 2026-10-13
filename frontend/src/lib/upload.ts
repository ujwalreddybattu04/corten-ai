/** Multipart upload with progress. An expired access token is refreshed once through the shared session client. */
import { api, ApiRequestError } from "./api";

export async function uploadWithProgress<T>(url: string, file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<T> {
    try {
        return await send<T>(url, file, onProgress, signal);
    } catch (error) {
        if (!(error instanceof ApiRequestError) || error.status !== 401) throw error;
        await api.get("/api/v1/auth/me");  // Refreshes the session or reports that sign-in is required.
        onProgress(0);
        return send<T>(url, file, onProgress, signal);
    }
}

/** XMLHttpRequest is the only browser API that reports upload progress. */
function send<T>(url: string, file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<T> {
    return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest();
        request.open("POST", url);
        request.withCredentials = true;
        request.responseType = "json";
        request.upload.onprogress = event => { if (event.lengthComputable) onProgress(event.loaded / event.total); };
        request.onload = () => {
            if (request.status >= 200 && request.status < 300) return resolve(request.response as T);
            const detail = (request.response as { detail?: unknown } | null)?.detail;
            reject(new ApiRequestError(typeof detail === "string" ? detail
                : request.status === 401 ? "Your session expired. Sign in again and retry."
                : request.status === 413 ? "This file is larger than 25 MB." : "The upload failed. Please retry.", request.status));
        };
        request.onerror = () => reject(new ApiRequestError("The connection was interrupted. Please retry the upload.", 0));
        request.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
        signal?.addEventListener("abort", () => request.abort(), { once: true });
        const form = new FormData();
        form.append("file", file);
        request.send(form);
    });
}
