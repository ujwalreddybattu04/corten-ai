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
