"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { attachmentProblem, uploadAttachment, MAX_ATTACHMENTS, type AttachmentRef } from "@/lib/chatApi";

export interface PendingAttachment {
    key: string;
    name: string;
    size: number;
    image: boolean;
    progress: number;
    status: "uploading" | "ready" | "failed";
    error?: string;
    ref?: AttachmentRef;
    /** Local object URL for image thumbnails before and after upload. */
    preview?: string;
}

/** Files attached to the message being composed: validated, uploaded with progress, removable. */
export function useAttachments() {
    const [items, setItems] = useState<PendingAttachment[]>([]);
    const controllers = useRef(new Map<string, AbortController>());
    const previews = useRef(new Set<string>());

    useEffect(() => () => {
        controllers.current.forEach(controller => controller.abort());
        previews.current.forEach(url => URL.revokeObjectURL(url));
    }, []);

    const patch = (key: string, changes: Partial<PendingAttachment>) =>
        setItems(current => current.map(item => item.key === key ? { ...item, ...changes } : item));

    // Uploads start outside state updaters, which React may run more than once.
    const count = useRef(0);
    useEffect(() => { count.current = items.filter(item => item.status !== "failed").length; }, [items]);

    const add = useCallback((files: FileList | File[]) => {
        const list = [...files];
        const room = Math.max(0, MAX_ATTACHMENTS - count.current);
        count.current += Math.min(room, list.length);
        const accepted = list.slice(0, room).map(file => {
            const image = file.type.startsWith("image/");
            const problem = attachmentProblem(file);
            const preview = image && !problem ? URL.createObjectURL(file) : undefined;
            if (preview) previews.current.add(preview);
            return { file, problem, item: { key: crypto.randomUUID(), name: file.name || "Pasted image", size: file.size, image,
                progress: 0, status: problem ? "failed" : "uploading", error: problem ?? undefined, preview } as PendingAttachment };
        });
        const skipped = list.length - accepted.length;
        const notice: PendingAttachment[] = skipped > 0 ? [{ key: crypto.randomUUID(), name: `${skipped} more file${skipped === 1 ? "" : "s"}`,
            size: 0, image: false, progress: 0, status: "failed", error: `You can attach up to ${MAX_ATTACHMENTS} files per message.` }] : [];
        setItems(current => [...current, ...accepted.map(entry => entry.item), ...notice]);
        for (const { file, problem, item } of accepted) {
            if (problem) continue;
            const controller = new AbortController();
            controllers.current.set(item.key, controller);
            uploadAttachment(file, progress => patch(item.key, { progress }), controller.signal)
                .then(ref => patch(item.key, { status: "ready", progress: 1, ref }))
                .catch(error => {
                    if (error instanceof DOMException && error.name === "AbortError") return;
                    patch(item.key, { status: "failed", error: error instanceof Error ? error.message : "Upload failed." });
                })
                .finally(() => controllers.current.delete(item.key));
        }
    }, []);

    const remove = useCallback((key: string) => {
        controllers.current.get(key)?.abort();
        setItems(current => {
            const item = current.find(entry => entry.key === key);
            if (item?.preview) { URL.revokeObjectURL(item.preview); previews.current.delete(item.preview); }
            return current.filter(entry => entry.key !== key);
        });
    }, []);

    /** Clear after sending. Object URLs are kept until unmount so sent thumbnails stay visible. */
    const clear = useCallback(() => setItems([]), []);

    return {
        items,
        add,
        remove,
        clear,
        ready: items.filter(item => item.status === "ready" && item.ref).map(item => item.ref!),
        uploading: items.some(item => item.status === "uploading"),
    };
}
