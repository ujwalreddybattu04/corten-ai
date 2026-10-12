/** Remote compilers are selected from the provider's current catalogue. */
const LANGUAGES: Record<string, string> = { c: "C", cpp: "C++", "c++": "C++", java: "Java", rust: "Rust", go: "Go", ruby: "Ruby", rb: "Ruby", php: "PHP", lua: "Lua", csharp: "C#", cs: "C#", swift: "Swift", bash: "Bash", sh: "Bash" };
let catalogue: { entries: Array<{ name: string; language: string }>; expires: number } | null = null;
let loading: Promise<Array<{ name: string; language: string }>> | null = null;
export function supportedLanguage(language: string) { return Object.hasOwn(LANGUAGES, language); }
export async function selectCompiler(language: string): Promise<string | null> {
    if (!supportedLanguage(language)) return null;
    if (!catalogue || catalogue.expires < Date.now()) {
        if (!loading) loading = (async () => {
            const response = await fetch("https://wandbox.org/api/list.json", { signal: AbortSignal.timeout(8000), cache: "no-store" });
            if (!response.ok) throw new Error("Compiler catalogue unavailable");
            const raw = await response.json();
            if (!Array.isArray(raw) || raw.length > 3000 || raw.some(item => typeof item?.name !== "string" || typeof item?.language !== "string")) throw new Error("Invalid compiler catalogue");
            catalogue = { entries: raw, expires: Date.now()+300000 };
            return raw;
        })().finally(() => { loading = null; });
        await loading;
    }
    const available = catalogue!.entries.filter(item => item.language === LANGUAGES[language] || (["sh", "bash"].includes(language) && item.name === "bash"));
    const stable = available.filter(item => !/head|nightly|experimental/i.test(item.name));
    const choices = stable.length ? stable : available;
    choices.sort((a, b) => b.name.localeCompare(a.name, undefined, { numeric: true }));
    return choices[0]?.name || null;
}

export async function readExecutionInput(request: Request) {
    const reader = request.body?.getReader();
    if (!reader) throw new Error("Invalid JSON body");
    const chunks: Uint8Array[] = []; let size = 0;
    try {
        while (true) { const item = await reader.read(); if (item.done) break; size += item.value.byteLength; if (size > 300000) { await reader.cancel(); throw new Error("Request too large (max 300 KB)"); } chunks.push(item.value); }
    } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    const body: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("Invalid JSON body");
    const { language, code, stdin = "" } = body as Record<string, unknown>;
    if (typeof language !== "string" || language.length > 30 || typeof code !== "string" || !code.trim() || code.length > 100000 || typeof stdin !== "string" || stdin.length > 20000) throw new Error("Provide a supported language, code up to 100 KB and input up to 20 KB");
    return { language: language.toLowerCase(), code, stdin };
}
