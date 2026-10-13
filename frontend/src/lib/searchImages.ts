import type { SearchImage } from "@/hooks/useSearch";

/** Prevent mixed-content images and executable links, including saved legacy data. */
export function imageUrl(value: unknown, allowData = false): string {
    if (typeof value !== "string" || !value || value.length > (allowData ? 2_000_000 : 4096)) return "";
    if (allowData && /^data:image\/(?:png|jpeg|gif|webp|svg\+xml);base64,[a-zA-Z0-9+/=]+$/.test(value)) return value;
    try {
        const url = new URL(value);
        return url.protocol === "https:" && !url.username && !url.password ? value : "";
    } catch { return ""; }
}

export function imageCandidates(image: SearchImage, preview = true): string[] {
    const values = preview ? [image.thumbnailUrl, image.url] : [image.url, image.thumbnailUrl];
    return [...new Set(values.map(url => imageUrl(url, true)).filter(Boolean))];
}
