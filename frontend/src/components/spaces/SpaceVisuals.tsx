import {
    Bookmark, FolderOpen, BookOpen, Briefcase, Code, Lightbulb, GraduationCap, Beaker, PenTool, TrendingUp,
} from "lucide-react";
import type { SpaceRole } from "@/lib/spacesApi";
import { ROLE_LABELS } from "@/lib/spacesApi";

/** Emoji offered by the icon picker; the server accepts exactly these. */
export const SPACE_EMOJI = ["💊", "🧬", "🔬", "🧪", "🏥", "📊", "📈", "💼", "🏛️", "⚖️", "🌍", "🚀", "🎯", "💡", "🧠", "📚",
    "📝", "🗂️", "📌", "🔍", "🤝", "🛠️", "💻", "🎓", "✈️", "🏠", "🎨", "📣", "💰", "🗓️", "⭐", "🌱"];
export const DEFAULT_SPACE_ICON = "📚";

// Icons from the first Spaces design, still used by existing Spaces.
const LEGACY_ICONS: Record<string, typeof Bookmark> = {
    bookmark: Bookmark, folder: FolderOpen, book: BookOpen, briefcase: Briefcase, code: Code, lightbulb: Lightbulb,
    graduation: GraduationCap, beaker: Beaker, pen: PenTool, trending: TrendingUp,
};

/** A Space's icon: an emoji, or a line icon for Spaces created before emoji were available. */
export function SpaceIcon({ icon, size = 40, tile = true, className = "" }: { icon: string; size?: number; tile?: boolean; className?: string }) {
    const Legacy = LEGACY_ICONS[icon];
    return (
        <span className={`sv-icon ${tile ? "sv-icon--tile" : ""} ${className}`} aria-hidden="true"
            style={{ width: size, height: size, fontSize: Math.round(size * (tile ? 0.5 : 0.82)) }}>
            {Legacy ? <Legacy size={Math.round(size * 0.46)} strokeWidth={1.75} /> : icon}
        </span>
    );
}

export function RoleBadge({ role }: { role: SpaceRole }) {
    return <span className={`sv-role sv-role--${role}`}>{ROLE_LABELS[role]}</span>;
}

const AVATAR_TINTS = ["#818cf8", "#2dd4bf", "#fb923c", "#f472b6", "#60a5fa", "#4ade80", "#facc15", "#a78bfa"];

export function initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function PersonAvatar({ name, size = 28 }: { name: string; size?: number }) {
    const tint = AVATAR_TINTS[[...name].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % AVATAR_TINTS.length];
    return (
        <span className="sx-avatar" aria-hidden="true"
            style={{ width: size, height: size, fontSize: size * 0.4, background: tint + "22", color: tint }}>
            {initials(name)}
        </span>
    );
}
