const { test } = require("node:test");
const assert = require("node:assert/strict");
const { progressiveText } = require("./load-ts")("src/lib/progressiveText.ts");

function setup() {
    let id = 0, time = 0, immediate = false, visibility;
    const frames = new Map(), updates = [], abort = new AbortController();
    const clock = {
        frame: fn => { frames.set(++id, fn); return id; },
        cancel: id => frames.delete(id),
        immediate: () => immediate,
        onVisibility: fn => { visibility = fn; return () => { visibility = undefined; }; },
    };
    const reveal = progressiveText(text => updates.push(text), abort.signal, clock);
    return { reveal, updates, abort, frames,
        tick() { time += 32; const work = [...frames.values()]; frames.clear(); work.forEach(fn => fn(time)); },
        flush() { for (let n = 0; frames.size && n < 1000; n++) this.tick(); assert.equal(frames.size, 0); },
        instant() { immediate = true; visibility?.(); },
    };
}

test("a cached response arriving in one chunk is revealed across frames without changing the answer", async () => {
    const s = setup(), answer = "### Evidence\n\nChinese 中文 and a complete answer. ".repeat(30);
    s.reveal.append(answer);
    let complete = false;
    const finished = s.reveal.finish().then(() => { complete = true; });
    assert.equal(s.updates.length, 0);
    s.tick(); await Promise.resolve();
    assert.ok(s.updates[0].length > 0 && s.updates[0].length < answer.length);
    assert.equal(complete, false);
    s.flush(); await finished;
    assert.equal(s.updates.at(-1), answer);
    assert.ok(s.updates.length > 20);
    assert.ok(s.updates.every((v, i) => answer.startsWith(v) && (!i || v.length >= s.updates[i - 1].length)));
    s.reveal.cancel();
});

test("reveal boundaries preserve complete graphemes and exact Markdown/Unicode", async () => {
    const s = setup(), answer = "👩🏽‍🔬 e\u0301 中文 👨‍👩‍👧‍👦 [1]\n".repeat(20);
    const boundaries = new Set([...new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(answer)].map(p => p.index + p.segment.length));
    s.reveal.append(answer); const finished = s.reveal.finish(); s.flush(); await finished;
    assert.ok(s.updates.every(text => boundaries.has(text.length)));
    assert.equal(s.updates.at(-1), answer);
    s.reveal.cancel();
});

test("a complete answer is revealed at word boundaries rather than split English words", async () => {
    const s = setup(), answer = "Regulatory evidence supports this specific labeling change. ".repeat(15);
    const boundaries = new Set([...new Intl.Segmenter(undefined, { granularity: "word" }).segment(answer)].map(p => p.index + p.segment.length));
    s.reveal.append(answer); const finished = s.reveal.finish(); s.flush(); await finished;
    assert.ok(s.updates.length > 20 && s.updates.every(text => boundaries.has(text.length)));
    assert.equal(s.updates.at(-1), answer); s.reveal.cancel();
});

test("multiple network chunks keep order, and showing all does not lose later chunks", async () => {
    const s = setup(); s.reveal.append("First "); s.tick();
    s.reveal.append("second "); s.reveal.showAll();
    assert.equal(s.updates.at(-1), "First second ");
    s.reveal.append("last."); await s.reveal.finish();
    assert.equal(s.updates.at(-1), "First second last.");
    assert.equal(s.frames.size, 0); s.reveal.cancel();
});

test("reduced-motion or a hidden tab flushes immediately without waiting for animation frames", async () => {
    const s = setup(); s.reveal.append("A long answer ".repeat(100));
    const finished = s.reveal.finish(); s.instant(); await finished;
    assert.equal(s.updates.at(-1), "A long answer ".repeat(100));
    assert.equal(s.frames.size, 0); s.reveal.cancel();
    const initial = setup(); initial.instant(); initial.reveal.append("No animation");
    assert.equal(initial.updates.at(-1), "No animation"); initial.reveal.cancel();
});

test("navigation/abort cancels pending frames and releases completion without publishing more text", async () => {
    const s = setup(); s.reveal.append("Do not save partial text. ".repeat(40));
    const finished = s.reveal.finish(); s.tick(); const prior = [...s.updates];
    s.abort.abort(); await finished; s.tick(); s.reveal.append("unwanted"); s.reveal.showAll();
    assert.deepEqual(s.updates, prior); assert.equal(s.frames.size, 0);
});

test("a failed reader can discard its reveal without waiting for all queued text", () => {
    const s = setup(); s.reveal.append("Draft that must never become a saved success".repeat(30));
    s.reveal.cancel(); s.tick(); assert.equal(s.updates.length, 0); assert.equal(s.frames.size, 0);
});
