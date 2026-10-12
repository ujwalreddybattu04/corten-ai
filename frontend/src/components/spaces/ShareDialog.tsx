"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { X, Link2, Copy, Check, Mail, Loader2, LogOut, Trash2, Clock } from "lucide-react";
import { useModalFocus } from "@/hooks/useModalFocus";
import {
    spacesApi, inviteUrl, ROLE_DESCRIPTIONS, ROLE_LABELS,
    type Space, type SpaceInvite, type SpaceMember, type SpaceRole,
} from "@/lib/spacesApi";
import { PersonAvatar, RoleBadge } from "./SpaceVisuals";

type InviteRole = Exclude<SpaceRole, "owner">;

function CopyField({ value, label }: { value: string; label: string }) {
    const [copied, setCopied] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);
    const copy = async () => {
        try { await navigator.clipboard.writeText(value); }
        catch { inputRef.current?.select(); return; }
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };
    return (
        <div className="sx-copy">
            <input ref={inputRef} className="sx-input sx-copy-input" readOnly value={value} aria-label={label} onFocus={event => event.target.select()} />
            <button type="button" className="sx-btn sx-btn--secondary" onClick={copy}>
                {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
            </button>
        </div>
    );
}

function RoleSelect({ value, onChange, disabled, allowOwner = false, id }: {
    value: SpaceRole; onChange: (role: SpaceRole) => void; disabled?: boolean; allowOwner?: boolean; id?: string;
}) {
    return (
        <select id={id} className="sx-select" value={value} disabled={disabled} onChange={event => onChange(event.target.value as SpaceRole)}
            aria-label="Access level">
            <option value="editor">{ROLE_LABELS.editor}</option>
            <option value="viewer">{ROLE_LABELS.viewer}</option>
            {allowOwner && <option value="owner">Make owner…</option>}
        </select>
    );
}

export default function ShareDialog({ space, onClose, onChanged, onLeft }: {
    space: Space; onClose: () => void; onChanged: () => void; onLeft: () => void;
}) {
    const owner = space.role === "owner";
    const [members, setMembers] = useState<SpaceMember[]>([]);
    const [invites, setInvites] = useState<SpaceInvite[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [email, setEmail] = useState("");
    const [emailRole, setEmailRole] = useState<InviteRole>("editor");
    const [linkRole, setLinkRole] = useState<InviteRole>("viewer");
    const [created, setCreated] = useState<{ url: string; email: string | null } | null>(null);
    const [busy, setBusy] = useState("");
    const [confirm, setConfirm] = useState<{ kind: "remove" | "owner" | "leave"; member?: SpaceMember } | null>(null);
    const dialogRef = useRef<HTMLDivElement>(null);
    useModalFocus(dialogRef, true, onClose);

    const load = useCallback(() => spacesApi.members(space.id).then(result => {
        setMembers(result.members);
        setInvites(result.invites);
        setError("");
    }, failure => {
        setError(failure instanceof Error ? failure.message : "Members could not be loaded.");
    }).finally(() => setLoading(false)), [space.id]);
    useEffect(() => { void load(); }, [load]);

    const run = async (key: string, action: () => Promise<unknown>, after?: () => void) => {
        setBusy(key);
        setError("");
        try { await action(); after?.(); await load(); onChanged(); }
        catch (failure) { setError(failure instanceof Error ? failure.message : "The change could not be saved."); }
        finally { setBusy(""); }
    };

    const inviteByEmail = (event: React.FormEvent) => {
        event.preventDefault();
        const address = email.trim();
        if (!address) return;
        void run("email", async () => {
            const result = await spacesApi.invite(space.id, emailRole, address);
            setCreated({ url: inviteUrl(result.token), email: result.invite.email });
            setEmail("");
        });
    };
    const createLink = () => run("link", async () => {
        const result = await spacesApi.invite(space.id, linkRole);
        setCreated({ url: inviteUrl(result.token), email: null });
    });

    const confirmAction = () => {
        if (!confirm) return;
        const { kind, member } = confirm;
        setConfirm(null);
        if (kind === "leave") {
            const me = members.find(item => item.isYou);
            if (me) void run("leave", () => spacesApi.removeMember(space.id, me.userId), onLeft);
        } else if (member && kind === "remove") {
            void run(member.userId, () => spacesApi.removeMember(space.id, member.userId));
        } else if (member && kind === "owner") {
            void run(member.userId, () => spacesApi.changeRole(space.id, member.userId, "owner"));
        }
    };

    return (
        <div className="sp-spaces-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
            <div ref={dialogRef} className="sx-dialog sx-share" role="dialog" aria-modal="true" aria-labelledby="share-title">
                <header className="sx-dialog-header">
                    <div>
                        <h2 id="share-title">Share “{space.name}”</h2>
                        <p className="sx-muted">Members see this Space&apos;s threads, files, links and instructions.</p>
                    </div>
                    <button className="sp-spaces-form-close" aria-label="Close" onClick={onClose}><X size={18} /></button>
                </header>

                <div className="sx-dialog-body">
                    {owner && (
                        <section className="sx-share-section" aria-labelledby="invite-heading">
                            <h3 id="invite-heading" className="sx-section-title">Invite people</h3>
                            <form className="sx-invite-row" onSubmit={inviteByEmail}>
                                <div className="sx-input-icon">
                                    <Mail size={15} aria-hidden="true" />
                                    <input className="sx-input" type="email" autoComplete="off" placeholder="name@company.com" value={email}
                                        aria-label="Email address" maxLength={254} onChange={event => setEmail(event.target.value)} />
                                </div>
                                <RoleSelect value={emailRole} onChange={role => setEmailRole(role as InviteRole)} />
                                <button className="sx-btn sx-btn--primary" disabled={!email.trim() || busy === "email"}>
                                    {busy === "email" ? <Loader2 size={14} className="sx-spin" /> : null} Invite
                                </button>
                            </form>
                            <div className="sx-link-row">
                                <span className="sx-link-row-label"><Link2 size={15} aria-hidden="true" /> Anyone with an invitation link can join as</span>
                                <RoleSelect value={linkRole} onChange={role => setLinkRole(role as InviteRole)} />
                                <button type="button" className="sx-btn sx-btn--secondary" onClick={() => void createLink()} disabled={busy === "link"}>
                                    {busy === "link" ? <Loader2 size={14} className="sx-spin" /> : null} Create link
                                </button>
                            </div>
                            {created && (
                                <div className="sx-created" role="status">
                                    <p>{created.email
                                        ? <>Invitation ready for <strong>{created.email}</strong>. It appears when they sign in with that address. You can also send them this private link (valid for 14 days):</>
                                        : <>Invitation link created. It works for 7 days and can be revoked below. Share it only with people who should join.</>}</p>
                                    <CopyField value={created.url} label="Invitation link" />
                                </div>
                            )}
                        </section>
                    )}

                    {error && <p className="sx-error" role="alert">{error}</p>}

                    <section className="sx-share-section" aria-labelledby="members-heading">
                        <h3 id="members-heading" className="sx-section-title">
                            Members {!loading && <span className="sx-count">{members.length}</span>}
                        </h3>
                        {loading ? (
                            <div className="sx-skeleton-list">{[0, 1, 2].map(i => <div key={i} className="sx-skeleton sx-skeleton--row" />)}</div>
                        ) : (
                            <ul className="sx-member-list">
                                {members.map(member => (
                                    <li key={member.userId} className="sx-member">
                                        <PersonAvatar name={member.name} size={34} />
                                        <div className="sx-member-text">
                                            <span className="sx-member-name">{member.name}{member.isYou && <span className="sx-you">You</span>}</span>
                                            {member.email && <span className="sx-muted sx-ellipsis">{member.email}</span>}
                                        </div>
                                        {owner && member.role !== "owner" ? (
                                            <div className="sx-member-actions">
                                                <RoleSelect value={member.role} allowOwner disabled={busy === member.userId}
                                                    onChange={role => role === "owner" ? setConfirm({ kind: "owner", member })
                                                        : void run(member.userId, () => spacesApi.changeRole(space.id, member.userId, role))} />
                                                <button className="sx-icon-btn sx-icon-btn--danger" aria-label={`Remove ${member.name}`} title="Remove from Space"
                                                    onClick={() => setConfirm({ kind: "remove", member })}><Trash2 size={14} /></button>
                                            </div>
                                        ) : <RoleBadge role={member.role} />}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    {owner && invites.length > 0 && (
                        <section className="sx-share-section" aria-labelledby="pending-heading">
                            <h3 id="pending-heading" className="sx-section-title">Pending invitations <span className="sx-count">{invites.length}</span></h3>
                            <ul className="sx-member-list">
                                {invites.map(invite => (
                                    <li key={invite.id} className="sx-member">
                                        <span className="sx-avatar sx-avatar--pending" aria-hidden="true">{invite.kind === "email" ? <Mail size={14} /> : <Link2 size={14} />}</span>
                                        <div className="sx-member-text">
                                            <span className="sx-member-name sx-ellipsis">{invite.email ?? "Invitation link"}</span>
                                            <span className="sx-muted"><Clock size={11} aria-hidden="true" /> {ROLE_LABELS[invite.role]} · expires {new Date(invite.expiresAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
                                        </div>
                                        <button className="sx-btn sx-btn--ghost" disabled={busy === invite.id}
                                            onClick={() => void run(invite.id, () => spacesApi.revokeInvite(space.id, invite.id))}>Revoke</button>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}

                    <dl className="sx-role-legend">
                        {(["owner", "editor", "viewer"] as SpaceRole[]).map(role => (
                            <div key={role}><dt>{ROLE_LABELS[role]}</dt><dd>{ROLE_DESCRIPTIONS[role]}</dd></div>
                        ))}
                    </dl>
                </div>

                <footer className="sx-dialog-footer">
                    {!owner ? (
                        <button className="sx-btn sx-btn--danger-ghost" onClick={() => setConfirm({ kind: "leave" })} disabled={busy === "leave"}>
                            <LogOut size={14} /> Leave Space
                        </button>
                    ) : <span className="sx-muted">Your role: Owner</span>}
                    <button className="sx-btn sx-btn--secondary" onClick={onClose}>Done</button>
                </footer>

                {confirm && (
                    <div className="sx-confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-text">
                        <h3 id="confirm-title">{confirm.kind === "leave" ? "Leave this Space?" : confirm.kind === "owner" ? "Transfer ownership?" : "Remove member?"}</h3>
                        <p id="confirm-text">
                            {confirm.kind === "leave" && "You will lose access to its threads and files. An owner can invite you again."}
                            {confirm.kind === "owner" && <><strong>{confirm.member?.name}</strong> will become the owner. You will keep edit access but can no longer manage members or delete the Space.</>}
                            {confirm.kind === "remove" && <><strong>{confirm.member?.name}</strong> will lose access immediately. Threads they saved stay in the Space.</>}
                        </p>
                        <div className="sx-confirm-actions">
                            <button className="sx-btn sx-btn--secondary" autoFocus onClick={() => setConfirm(null)}>Cancel</button>
                            <button className="sx-btn sx-btn--danger" onClick={confirmAction}>
                                {confirm.kind === "leave" ? "Leave" : confirm.kind === "owner" ? "Transfer" : "Remove"}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
