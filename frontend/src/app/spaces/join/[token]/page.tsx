"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Loader2, AlertCircle, ArrowRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { spacesApi, ROLE_DESCRIPTIONS, type InvitePreview } from "@/lib/spacesApi";
import { RoleBadge, SpaceIcon } from "@/components/spaces/SpaceVisuals";

export default function JoinSpacePage() {
    const token = String(useParams().token ?? "");
    const router = useRouter();
    const { user } = useAuth();
    const [preview, setPreview] = useState<InvitePreview | null>(null);
    const [error, setError] = useState("");
    const [joining, setJoining] = useState(false);

    useEffect(() => {
        spacesApi.previewLink(token).then(setPreview)
            .catch(failure => setError(failure instanceof Error ? failure.message : "This invitation could not be opened."));
    }, [token]);

    const join = async () => {
        setJoining(true);
        setError("");
        try {
            const result = await spacesApi.acceptLink(token);
            router.replace(`/spaces/${result.spaceId}`);
        } catch (failure) {
            setError(failure instanceof Error ? failure.message : "You could not join this Space.");
            setJoining(false);
        }
    };

    return (
        <div className="sx-join">
            <div className="sx-join-card">
                {!preview && !error && <div className="sx-join-loading" role="status"><Loader2 size={20} className="sx-spin" /> Opening invitation…</div>}
                {error && !preview && (
                    <div role="alert" className="sx-join-error">
                        <AlertCircle size={28} aria-hidden="true" />
                        <h1>Invitation unavailable</h1>
                        <p>{error}</p>
                        <Link href="/spaces" className="sx-btn sx-btn--secondary">Go to Spaces</Link>
                    </div>
                )}
                {preview && (
                    <>
                        <SpaceIcon icon={preview.icon} color={preview.color} size={30} box={64} />
                        <p className="sx-muted">{preview.inviterName} invited you to join</p>
                        <h1>{preview.name}</h1>
                        {preview.description && <p className="sx-join-description">{preview.description}</p>}
                        <div className="sx-join-role"><RoleBadge role={preview.role} /><span className="sx-muted">{ROLE_DESCRIPTIONS[preview.role]}</span></div>
                        {preview.emailMismatch ? (
                            <p className="sx-warning" role="alert"><AlertCircle size={14} aria-hidden="true" /> This invitation was sent to a different email address than {user?.email}. Sign in with the invited account to accept it.</p>
                        ) : preview.memberRole ? (
                            <Link href={`/spaces/${preview.spaceId}`} className="sx-btn sx-btn--primary sx-btn--wide">You&apos;re already a member · Open Space <ArrowRight size={14} /></Link>
                        ) : (
                            <button className="sx-btn sx-btn--primary sx-btn--wide" onClick={() => void join()} disabled={joining}>
                                {joining && <Loader2 size={14} className="sx-spin" />} Join as {preview.role === "editor" ? "editor" : "viewer"}
                            </button>
                        )}
                        {error && <p className="sx-error" role="alert">{error}</p>}
                        <p className="sx-join-fineprint">Signed in as {user?.email}. Members can see the Space&apos;s threads, files and instructions.</p>
                    </>
                )}
            </div>
        </div>
    );
}
