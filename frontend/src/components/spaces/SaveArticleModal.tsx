"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, Loader2 } from "lucide-react";
import { useModalFocus } from "@/hooks/useModalFocus";
import { ApiRequestError } from "@/lib/api";
import { spacesApi, canEdit, normalizeLink, type Space } from "@/lib/spacesApi";
import { SpaceIcon } from "./SpaceVisuals";

/** Save a publisher's original article URL as a trusted link in a Space the user can edit. */
export default function SaveArticleModal({ article, onClose }: { article: { title: string; url: string }; onClose: () => void }) {
    const ref = useRef<HTMLDivElement>(null);
    const [spaces, setSpaces] = useState<Space[] | null>(null);
    const [saving, setSaving] = useState("");
    const [saved, setSaved] = useState("");
    const [message, setMessage] = useState("");
    useModalFocus(ref, true, onClose);

    useEffect(() => {
        spacesApi.list().then(list => setSpaces(list.filter(space => canEdit(space.role))))
            .catch(() => { setSpaces([]); setMessage("Your Spaces could not be loaded. Please retry."); });
    }, []);

    const save = async (space: Space) => {
        const link = normalizeLink(article.url);
        if (!link) { setMessage("This article does not have a web address that can be saved."); return; }
        setSaving(space.id);
        setMessage("");
        try {
            // Re-read so another member's recent link edits are kept.
            for (let attempt = 0; attempt < 2; attempt++) {
                const latest = await spacesApi.get(space.id);
                if (latest.links.includes(link)) break;
                if (latest.links.length >= 100) throw new Error("This Space already has the maximum of 100 links.");
                try { await spacesApi.update(latest, { links: [...latest.links, link] }); break; }
                catch (failure) { if (!(failure instanceof ApiRequestError && failure.status === 409) || attempt) throw failure; }
            }
            setSaved(space.id);
            setMessage(`Saved to ${space.name}. Answers in that Space will search this site first.`);
        } catch (failure) {
            setMessage(failure instanceof Error ? failure.message : "The link could not be saved. Please retry.");
        } finally { setSaving(""); }
    };

    return (
        <div className="tdm-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
            <div className="tdm-modal" ref={ref} role="dialog" aria-modal="true" aria-labelledby="save-article-title">
                <h3 className="tdm-modal-title" id="save-article-title">Save to Space</h3>
                <p className="tdm-modal-msg sx-ellipsis">{article.title}</p>
                <div className="tdm-space-list sx-pick-list">
                    {spaces === null ? <p className="sx-muted" role="status"><Loader2 size={14} className="sx-spin" /> Loading Spaces…</p>
                        : spaces.length ? spaces.map(space => (
                            <button className="tdm-item sx-pick" key={space.id} disabled={!!saving} onClick={() => void save(space)}>
                                <SpaceIcon icon={space.icon} size={26} />
                                <span className="sx-ellipsis">{space.name}</span>
                                {saving === space.id ? <Loader2 size={14} className="sx-spin" /> : saved === space.id ? <Check size={14} /> : null}
                            </button>
                        )) : <p className="sx-muted"><Link href="/spaces">Create a Space</Link> to save this article.</p>}
                </div>
                {message && <p className="tdm-modal-msg" role="status">{message}</p>}
                <div className="tdm-modal-actions"><button className="tdm-modal-btn tdm-modal-btn--cancel" onClick={onClose}>Close</button></div>
            </div>
        </div>
    );
}
