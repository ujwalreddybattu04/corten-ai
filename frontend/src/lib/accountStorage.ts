/** Browser records are isolated by the server-verified account. Guest data stays intact. */
let account: string | null = null;
let legacyOwner: string | null = null;
const observers = new Set<(name: string, before: string | null, after: string | null) => void>();
export function observeAccountWrites(observer: (name: string, before: string | null, after: string | null) => void) {
    observers.add(observer);
    return () => { observers.delete(observer); };
}
export function protectLegacyAccountData() {
    try {
        const saved = localStorage.getItem("corten_legacy_owner") || JSON.parse(localStorage.getItem("corten_user") || "null")?.id;
        if (typeof saved === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(saved)) {
            legacyOwner = saved;
            localStorage.setItem("corten_legacy_owner", saved);
        }
    } catch { /* A cached profile never establishes authentication. */ }
}
export const setStorageAccount = (id: string | null) => { account = id; };
export const getStorageAccount = () => account;
const key = (name: string) => account ? `corten_account:${account}:${name}` : legacyOwner ? `corten_account:guest:${name}` : name;
export const accountStorage = {
    getItem: (name: string) => localStorage.getItem(key(name)) ?? (account && account === legacyOwner ? localStorage.getItem(name) : null),
    setItem: (name: string, value: string) => {
        const before = accountStorage.getItem(name);
        localStorage.setItem(key(name), value);
        if (before !== value) for (const observer of observers) { try { observer(name, before, value); } catch { /* Local saves remain usable during a sync failure. */ } }
    },
    removeItem: (name: string) => {
        const before = accountStorage.getItem(name);
        localStorage.removeItem(key(name));
        if (before !== null) for (const observer of observers) { try { observer(name, before, null); } catch { /* Local deletion is independent of networking. */ } }
    },
};
export function safeReturnPath(value: string | null): string {
    if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f]/.test(value)) return "/";
    try {
        const url = new URL(value, "https://corten.invalid");
        const pathname = decodeURIComponent(url.pathname);
        return url.origin === "https://corten.invalid" && !pathname.startsWith("/auth") && !pathname.startsWith("//") && !/[\\\u0000-\u001f]/.test(pathname) ? url.pathname + url.search + url.hash : "/";
    } catch { return "/"; }
}
