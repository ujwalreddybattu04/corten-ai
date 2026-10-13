"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Stage = "idle" | "covering" | "revealing";
const EXIT_MS = 180;
const REVEAL_MS = 260;

/** Lives above the account-keyed views so session hydration cannot remove it. */
export function useSignInTransition(pathname: string, ready: boolean) {
    const [stage, setStage] = useState<Stage>("idle");
    const deadline = useRef<ReturnType<typeof setTimeout> | null>(null);
    const cancel = useCallback(() => {
        if (deadline.current !== null) clearTimeout(deadline.current);
        deadline.current = null;
        setStage("idle");
    }, []);
    const begin = useCallback(async () => {
        if (deadline.current !== null) clearTimeout(deadline.current);
        setStage("covering");
        // A failed/stalled navigation must never leave the page permanently inert.
        deadline.current = setTimeout(cancel, 8000);
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        await new Promise<void>(resolve => setTimeout(resolve, reduce ? 0 : EXIT_MS));
    }, [cancel]);

    useEffect(() => {
        if (stage !== "covering" || !ready || pathname.startsWith("/auth/")) return;
        let secondFrame = 0;
        // Paint the mounted destination before fading the cover away.
        const firstFrame = requestAnimationFrame(() => {
            secondFrame = requestAnimationFrame(() => setStage("revealing"));
        });
        return () => { cancelAnimationFrame(firstFrame); cancelAnimationFrame(secondFrame); };
    }, [stage, pathname, ready]);

    useEffect(() => {
        if (stage !== "revealing") return;
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const timer = setTimeout(() => {
            cancel();
            // The new page was inert during the reveal, including its autofocus.
            requestAnimationFrame(() => {
                const target = document.querySelector<HTMLElement>("#search-input") ||
                    document.querySelector<HTMLElement>("main h1, main");
                if (!target || document.activeElement !== document.body) return;
                if (!target.matches("input, button, a, textarea, [tabindex]")) target.tabIndex = -1;
                target.focus({ preventScroll: true });
            });
        }, reduce ? 0 : REVEAL_MS);
        return () => clearTimeout(timer);
    }, [stage, cancel]);

    useEffect(() => () => { if (deadline.current !== null) clearTimeout(deadline.current); }, []);
    return { stage, active: stage !== "idle", begin, cancel };
}
