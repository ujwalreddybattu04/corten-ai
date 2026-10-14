/** Pace display independently of network chunks. Persistence still waits for stream completion. */
interface RevealClock {
    frame: (callback: (time: number) => void) => number;
    cancel: (id: number) => void;
    immediate: () => boolean;
    onVisibility?: (callback: () => void) => () => void;
}

const browserClock = (): RevealClock => ({
    frame: callback => requestAnimationFrame(callback),
    cancel: id => cancelAnimationFrame(id),
    immediate: () => document.hidden || window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    onVisibility: callback => {
        document.addEventListener("visibilitychange", callback);
        return () => document.removeEventListener("visibilitychange", callback);
    },
});

export function progressiveText(update: (text: string) => void, signal: AbortSignal, clock = browserClock()) {
    let text = "", visible = 0, frame = 0, last = 0, ended = false, closed = false, instant = false;
    let resolve: (() => void) | undefined;
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    const stopFrame = () => { if (frame) clock.cancel(frame); frame = 0; };
    const settled = () => { if (ended && visible === text.length) { resolve?.(); resolve = undefined; } };
    const flush = () => {
        stopFrame();
        if (!closed && visible !== text.length) { visible = text.length; update(text); }
        settled();
    };
    const tick = (time: number) => {
        frame = 0;
        if (closed) return;
        if (instant || clock.immediate()) { flush(); return; }
        const elapsed = last ? Math.min(time - last, 80) : 32;
        if (elapsed < 28) { frame = clock.frame(tick); return; }
        last = time;
        const target = Math.min(text.length, visible + Math.max(1, Math.floor(elapsed * Math.max(320, (text.length - visible) / 6) / 1000)));
        // Preserve emoji, combining marks and non-Latin graphemes at every display boundary.
        let boundary = visible;
        for (const part of segmenter.segment(text.slice(visible))) {
            boundary = visible + part.index + part.segment.length;
            if (boundary >= target) break;
        }
        visible = boundary;
        update(text.slice(0, visible));
        if (visible < text.length) frame = clock.frame(tick);
        else { last = 0; settled(); }
    };
    const schedule = () => {
        if (instant || clock.immediate()) flush();
        else if (!frame && visible < text.length) frame = clock.frame(tick);
    };
    const cancel = () => {
        closed = true; stopFrame(); cleanupVisibility?.(); signal.removeEventListener("abort", cancel);
        resolve?.(); resolve = undefined;
    };
    const cleanupVisibility = clock.onVisibility?.(() => { if (clock.immediate()) flush(); });
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
    return {
        append(chunk: string) { if (!closed && !ended) { text += chunk; schedule(); } },
        finish(): Promise<void> {
            ended = true;
            if (closed || visible === text.length) return Promise.resolve();
            return new Promise(done => { resolve = done; schedule(); });
        },
        showAll() { instant = true; flush(); },
        cancel,
    };
}
