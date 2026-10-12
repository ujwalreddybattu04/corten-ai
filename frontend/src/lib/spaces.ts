import { accountStorage } from "./accountStorage";

/** Associate only an existing Space in the active account's browser records. */
export function associateSpaceThread(spaceId: string, threadId: string): boolean {
    const raw = accountStorage.getItem("corten_spaces");
    if (!raw) return false;
    let spaces;
    try { spaces = JSON.parse(raw); } catch { return false; }
    if (!Array.isArray(spaces)) return false;
    const space = spaces.find(item => item?.id === spaceId);
    if (!space) return false;
    const ids = Array.isArray(space.threadIds) ? space.threadIds : [];
    if (!ids.includes(threadId)) {
        space.threadIds = [...ids, threadId];
        space.updatedAt = Date.now();
        accountStorage.setItem("corten_spaces", JSON.stringify(spaces));
    }
    return true;
}

/** Apply this view's edits without deleting unrelated records created in another tab. */
export function mergeSpaceEdits<T extends { id: string }>(before: T[], after: T[]): T[] {
    let current: T[];
    try { current = JSON.parse(accountStorage.getItem("corten_spaces") || "[]"); } catch { current = before; }
    if (!Array.isArray(current)) current = before;
    const prior = new Map(before.map(item => [item.id, item]));
    const next = new Map(after.map(item => [item.id, item]));
    const removals = new Set(before.filter(item => !next.has(item.id)).map(item => item.id));
    const changes = after.filter(item => JSON.stringify(item) !== JSON.stringify(prior.get(item.id)));
    const ids = new Set(changes.map(item => item.id));
    const merged = [...changes, ...current.filter(item => !removals.has(item.id) && !ids.has(item.id))];
    accountStorage.setItem("corten_spaces", JSON.stringify(merged));
    window.dispatchEvent(new Event("corten_spaces_updated"));
    return merged;
}

export function saveArticleReference(spaceId: string, url: string): boolean {
    let parsed: URL;
    try { parsed = new URL(url); } catch { return false; }
    if (!["http:", "https:"].includes(parsed.protocol)) return false;
    const raw = accountStorage.getItem("corten_spaces");
    if (!raw) return false;
    let spaces;
    try { spaces = JSON.parse(raw); } catch { return false; }
    if (!Array.isArray(spaces)) return false;
    const space = spaces.find(item => item?.id === spaceId);
    if (!space) return false;
    const links = Array.isArray(space.links) ? space.links : [];
    if (!links.includes(parsed.href)) { space.links = [...links, parsed.href]; space.updatedAt = Date.now(); accountStorage.setItem("corten_spaces", JSON.stringify(spaces)); window.dispatchEvent(new Event("corten_spaces_updated")); }
    return true;
}
