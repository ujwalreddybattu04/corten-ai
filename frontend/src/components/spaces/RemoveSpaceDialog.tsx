"use client";
import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useModalFocus } from "@/hooks/useModalFocus";
import { spacesApi, type Space } from "@/lib/spacesApi";

/** Confirms leaving (members) or permanently deleting (owner) a Space, stating the consequences. */
export default function RemoveSpaceDialog({ space, leave, userId, onClose, onDone }: {
    space: Space; leave: boolean; userId: string; onClose: () => void; onDone: () => void;
}) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const ref = useRef<HTMLDivElement>(null);
    useModalFocus(ref, true, () => { if (!busy) onClose(); });
    const confirm = async () => {
        setBusy(true);
        setError("");
        try {
            if (leave) await spacesApi.removeMember(space.id, userId);
            else await spacesApi.remove(space.id);
            onDone();
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "The Space could not be updated.");
            setBusy(false);
        }
    };
    return (
        <div className="sp-spaces-overlay" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
            <div ref={ref} className="sp-spaces-delete-modal sx-danger-dialog" role="alertdialog" aria-modal="true" aria-labelledby="remove-title" aria-describedby="remove-text">
                <h3 id="remove-title">{leave ? `Leave “${space.name}”?` : `Delete “${space.name}”?`}</h3>
                <p id="remove-text">{leave
                    ? "You will lose access to its threads and files. The owner can invite you again."
                    : `This permanently deletes the Space for all ${space.memberCount} member${space.memberCount === 1 ? "" : "s"}, including ${space.threadCount} shared thread${space.threadCount === 1 ? "" : "s"} and ${space.fileCount} file${space.fileCount === 1 ? "" : "s"}. Conversations in each person's own history are not affected.`}</p>
                {error && <p className="sx-error" role="alert">{error}</p>}
                <div className="sp-spaces-delete-actions">
                    <button className="sp-spaces-del-cancel" onClick={onClose} disabled={busy} autoFocus>Cancel</button>
                    <button className="sp-spaces-del-confirm" onClick={() => void confirm()} disabled={busy}>
                        {busy && <Loader2 size={14} className="sx-spin" />} {leave ? "Leave Space" : "Delete permanently"}
                    </button>
                </div>
            </div>
        </div>
    );
}
