import { accountStorage } from "./accountStorage";
import { normalizeLink } from "./spacesApi";

/** Spaces are server records now. This module only carries Spaces saved by the earlier
 *  browser-only design into the signed-in account, then removes the local copy. */
const LEGACY_KEY = "corten_spaces";
const ICONS = new Set(["bookmark", "folder", "book", "briefcase", "code", "lightbulb", "graduation", "beaker", "pen", "trending"]);

export interface LegacySpaceImport {
    legacyId: string;
    name: string;
    description: string;
    instructions: string;
    icon: string;
    color: string;
    links: string[];
    threads: Record<string, unknown>[];
}

function parse(raw: string | null): unknown[] {
    try { const value = JSON.parse(raw || "[]"); return Array.isArray(value) ? value : []; } catch { return []; }
}

const text = (value: unknown, limit: number) => (typeof value === "string" ? value.trim().slice(0, limit) : "");

export function legacyBrowserSpaces(): LegacySpaceImport[] {
    const threads = new Map<string, Record<string, unknown>>();
    for (const item of parse(accountStorage.getItem("corten_threads"))) {
        if (item && typeof item === "object" && typeof (item as { id?: unknown }).id === "string") threads.set((item as { id: string }).id, item as Record<string, unknown>);
    }
    const result: LegacySpaceImport[] = [];
    for (const item of parse(accountStorage.getItem(LEGACY_KEY))) {
        if (!item || typeof item !== "object") continue;
        const space = item as Record<string, unknown>;
        const legacyId = typeof space.id === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(space.id) ? space.id : "";
        const name = text(space.name, 100);
        if (!legacyId || !name) continue;
        const ids = Array.isArray(space.threadIds) ? space.threadIds.filter((id): id is string => typeof id === "string") : [];
        result.push({
            legacyId, name,
            description: text(space.description, 2000),
            instructions: text(space.instructions, 8000),
            icon: typeof space.icon === "string" && ICONS.has(space.icon) ? space.icon : "bookmark",
            color: typeof space.color === "string" && /^#[0-9a-fA-F]{6}$/.test(space.color) ? space.color : "#6366f1",
            links: [...new Set((Array.isArray(space.links) ? space.links : [])
                .map(link => typeof link === "string" ? normalizeLink(link) : null).filter((link): link is string => !!link))].slice(0, 100),
            threads: [...new Set(ids)].map(id => threads.get(id)).filter((thread): thread is Record<string, unknown> => !!thread).slice(0, 100),
        });
    }
    return result;
}

/** Remove only the Spaces the server confirmed, so a partial failure can be retried. */
export function clearLegacyBrowserSpaces(imported: string[]) {
    const done = new Set(imported);
    const remaining = parse(accountStorage.getItem(LEGACY_KEY)).filter(item =>
        !(item && typeof item === "object" && done.has((item as { id?: string }).id ?? "")));
    if (remaining.length) accountStorage.setItem(LEGACY_KEY, JSON.stringify(remaining));
    else accountStorage.removeItem(LEGACY_KEY);
}
