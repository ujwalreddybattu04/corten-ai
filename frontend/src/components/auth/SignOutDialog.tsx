"use client";

import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { LogOut, X } from "lucide-react";

export default function SignOutDialog({ onCancel, onConfirm }: {
    onCancel: () => void; onConfirm: () => void;
}) {
    const dialog = useRef<HTMLDialogElement>(null);
    const cancel = useRef<HTMLButtonElement>(null);
    const confirmed = useRef(false);
    useEffect(() => {
        const element = dialog.current;
        if (!element) return;
        const overflow = document.body.style.overflow;
        const previous = document.activeElement as HTMLElement | null;
        document.body.style.overflow = "hidden";
        if (!element.open) element.showModal();
        cancel.current?.focus();
        return () => {
            element.close(); document.body.style.overflow = overflow;
            if (previous?.isConnected) previous.focus({ preventScroll: true });
        };
    }, []);

    return createPortal(
        <dialog ref={dialog} className="signout-dialog" role="dialog" aria-modal="true"
            aria-labelledby="signout-title" aria-describedby="signout-description"
            onCancel={event => { event.preventDefault(); onCancel(); }}
            onKeyDown={event => {
                if (event.key !== "Tab") return;
                const controls = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not([disabled])")];
                const first = controls[0], last = controls.at(-1);
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }}
            onClick={event => {
                if (event.target !== event.currentTarget) return;
                const box = event.currentTarget.getBoundingClientRect();
                if (event.clientX < box.left || event.clientX > box.right ||
                    event.clientY < box.top || event.clientY > box.bottom) onCancel();
            }}>
            <button type="button" className="signout-close" aria-label="Close confirmation" onClick={onCancel}>
                <X size={18} aria-hidden="true" />
            </button>
            <div className="signout-icon"><LogOut size={22} aria-hidden="true" /></div>
            <h2 id="signout-title">Sign out of Corten?</h2>
            <p id="signout-description">You’ll need to sign in again to continue.</p>
            <div className="signout-actions">
                <button ref={cancel} type="button" className="signout-cancel" onClick={onCancel}>Cancel</button>
                <button type="button" className="signout-confirm" onClick={() => {
                    if (confirmed.current) return;
                    confirmed.current = true;
                    onConfirm();
                }}>Sign out</button>
            </div>
        </dialog>, document.body);
}
