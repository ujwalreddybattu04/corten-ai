"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { accountStorage } from "@/lib/accountStorage";
import { saveArticleReference } from "@/lib/spaces";
import CloudSyncStatus from "@/components/layout/CloudSyncStatus";

export default function SaveArticleModal({ article, onClose }: { article: { title: string; url: string }; onClose: () => void }) {
    const ref = useRef<HTMLDivElement>(null);
    const [spaces, setSpaces] = useState<Array<{ id: string; name: string }>>([]);
    const [message, setMessage] = useState("");
    useEffect(() => {
        const previous = document.activeElement as HTMLElement | null;
        try { const stored = JSON.parse(accountStorage.getItem("corten_spaces") || "[]"); setSpaces(Array.isArray(stored) ? stored.filter(item => typeof item?.id === "string" && typeof item?.name === "string") : []); } catch { setMessage("Unable to load your Spaces."); }
        const key = (event: KeyboardEvent) => {
            if (event.key === "Escape") { event.preventDefault(); onClose(); }
            if (event.key !== "Tab") return;
            const items = ref.current?.querySelectorAll<HTMLElement>("button:not([disabled]), a[href]");
            if (!items?.length) return;
            if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items[items.length-1].focus(); }
            else if (!event.shiftKey && document.activeElement === items[items.length-1]) { event.preventDefault(); items[0].focus(); }
        };
        ref.current?.querySelector<HTMLElement>("button, a[href]")?.focus();
        document.addEventListener("keydown", key);
        return () => { document.removeEventListener("keydown", key); previous?.focus(); };
    }, [onClose]);
    const save = (id: string) => {
        try { setMessage(saveArticleReference(id, article.url) ? "Reference link saved to Space." : "Unable to save this reference. Please retry."); }
        catch { setMessage("Device storage is unavailable. Please retry."); }
    };
    return <div className="tdm-overlay" onClick={onClose}>
        <div className="tdm-modal" ref={ref} role="dialog" aria-modal="true" aria-labelledby="save-article-title" onClick={event => event.stopPropagation()}>
            <h3 className="tdm-modal-title" id="save-article-title">Save to Space</h3>
            <p className="tdm-modal-msg">{article.title}</p>
            <p className="tdm-modal-msg">Save the publisher’s original link as a reference.</p>
            <div className="tdm-space-list">{spaces.length ? spaces.map(space => <button className="tdm-item" key={space.id} onClick={() => save(space.id)}>{space.name}</button>) : <p><Link href="/spaces">Create a Space</Link> to save this article.</p>}</div>
            {message && <p role="status">{message}</p>}
            <CloudSyncStatus />
            <div className="tdm-modal-actions"><button className="tdm-modal-btn tdm-modal-btn--cancel" onClick={onClose}>Close</button></div>
        </div>
    </div>;
}
