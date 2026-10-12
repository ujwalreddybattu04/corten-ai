"use client";
import { useEffect, useRef, type RefObject } from "react";

/** Keep keyboard interaction in the top visible dialog and restore its trigger. */
export function useModalFocus(ref: RefObject<HTMLElement | null>, open: boolean, onClose: () => void) {
    const close = useRef(onClose);
    close.current = onClose;
    useEffect(() => {
        const dialog = ref.current;
        if (!open || !dialog) return;
        const previous = document.activeElement as HTMLElement | null;
        const controls = () => [...dialog.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex="0"]')].filter(item => item.getClientRects().length > 0);
        const frame = requestAnimationFrame(() => controls()[0]?.focus());
        const key = (event: KeyboardEvent) => {
            const dialogs = [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')];
            if (dialogs.at(-1) !== dialog) return;
            if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); close.current(); }
            if (event.key !== "Tab") return;
            const items = controls();
            if (!items.length) return;
            if (!dialog.contains(document.activeElement) || (event.shiftKey && document.activeElement === items[0])) { event.preventDefault(); items.at(-1)?.focus(); }
            else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
        };
        document.addEventListener("keydown", key, true);
        return () => { cancelAnimationFrame(frame); document.removeEventListener("keydown", key, true); if (previous?.isConnected) previous.focus(); };
    }, [ref, open]);
}
