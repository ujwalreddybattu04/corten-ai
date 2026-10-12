import {
    Bookmark, FolderOpen, BookOpen, Briefcase, Code, Lightbulb, GraduationCap, Beaker, PenTool, TrendingUp,
    Crown, Pencil, Eye,
} from "lucide-react";
import type { SpaceRole } from "@/lib/spacesApi";
import { ROLE_LABELS } from "@/lib/spacesApi";

export const SPACE_ICONS = [
    { key: "bookmark", label: "Bookmark", Icon: Bookmark },
    { key: "folder", label: "Folder", Icon: FolderOpen },
    { key: "book", label: "Research", Icon: BookOpen },
    { key: "briefcase", label: "Work", Icon: Briefcase },
    { key: "code", label: "Code", Icon: Code },
    { key: "lightbulb", label: "Ideas", Icon: Lightbulb },
    { key: "graduation", label: "Learning", Icon: GraduationCap },
    { key: "beaker", label: "Science", Icon: Beaker },
    { key: "pen", label: "Writing", Icon: PenTool },
    { key: "trending", label: "Finance", Icon: TrendingUp },
] as const;

export const SPACE_COLORS = ["#6366f1", "#8b5cf6", "#ec4899", "#f43f5e", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#06b6d4", "#3b82f6"];

export function SpaceIcon({ icon, color, size = 22, box = 44, className = "" }: { icon: string; color: string; size?: number; box?: number; className?: string }) {
    const Icon = SPACE_ICONS.find(item => item.key === icon)?.Icon ?? Bookmark;
    return (
        <span className={`sx-space-icon ${className}`} aria-hidden="true"
            style={{ width: box, height: box, background: color + "1f", color, boxShadow: `inset 0 0 0 1px ${color}33` }}>
            <Icon size={size} />
        </span>
    );
}

const ROLE_ICONS = { owner: Crown, editor: Pencil, viewer: Eye };

export function RoleBadge({ role }: { role: SpaceRole }) {
    const Icon = ROLE_ICONS[role];
    return <span className={`sx-role sx-role--${role}`}><Icon size={11} aria-hidden="true" />{ROLE_LABELS[role]}</span>;
}

const AVATAR_TINTS = ["#6366f1", "#14b8a6", "#f97316", "#ec4899", "#3b82f6", "#22c55e", "#eab308", "#8b5cf6"];

export function initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] ?? "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function PersonAvatar({ name, size = 28 }: { name: string; size?: number }) {
    const tint = AVATAR_TINTS[[...name].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % AVATAR_TINTS.length];
    return (
        <span className="sx-avatar" aria-hidden="true"
            style={{ width: size, height: size, fontSize: size * 0.38, background: tint + "26", color: tint }}>
            {initials(name)}
        </span>
    );
}
