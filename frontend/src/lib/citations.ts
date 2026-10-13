/** Answer text, readied for display.
 *
 *  Citations: a run such as "[1][2][5][6]", "[2, 3]" or "【1†source】" becomes one source pill (a link to
 *  "#cite-1-2-5-6"), placed after the sentence's punctuation. Separate number chips cluttered the text and split
 *  "patterns 1 2 5 6 ." across lines. Code spans and fenced blocks are left untouched, and real Markdown links
 *  such as "[1](https://…)" stay links. */
const FULLWIDTH = /【(\d{1,2}(?:\s*[,，]\s*\d{1,2})*)(?:†[^】\n]{0,80})?】/g;
const CITATION_RUN = /(?:[ \t ]*\[\d{1,2}(?:\s*,\s*\d{1,2})*\](?![(:]))+([.,;:!?]*)/g;

export function linkCitations(markdown: string): string {
    return markdown.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map((part, index) => index % 2 ? part : part
        .replace(FULLWIDTH, "[$1]")
        .replace(CITATION_RUN, (run: string, punctuation: string) => {
            const numbers = [...new Set(run.slice(0, run.length - punctuation.length).match(/\d{1,2}/g) ?? [])];
            return `${punctuation}[${numbers.join(",")}](#cite-${numbers.join("-")})`;
        })).join("");
}

/** Citation numbers carried by a pill link ("#cite-1-2-5" -> [1, 2, 5]), or null for any other link. */
export function citationNumbers(href: string): number[] | null {
    const match = /^#cite-(\d{1,2}(?:-\d{1,2})*)$/.exec(href.trim());
    return match ? match[1].split("-").map(Number) : null;
}

/** How a source is named on its pill: its site ("aws.amazon.com"), or the file name for an attachment. */
export function sourceLabel(source: { domain?: string; title?: string; url?: string }): string {
    let host = (source.domain || "").trim();
    if (!host.includes(".") && source.url && /^https?:\/\//i.test(source.url)) {
        try { host = new URL(source.url).hostname; } catch { /* keep the given domain */ }
    }
    host = host.replace(/^www\./i, "");
    const label = host.includes(".") ? host : (source.title || host || "Source").trim();
    return label.length > 26 ? label.slice(0, 24).trimEnd() + "…" : label;
}

/** Researched answers open with the answer, never a heading. The prompts say so; this keeps it true when a model
 *  slips, and for answers saved before that rule ("## What is Deep Learning?" above the answer). A heading that
 *  restates a question goes in any answer; other headings stay where no sources were used, since a requested
 *  document ("write a blog post") may rightly carry a title. A heading still being streamed is handled the same way. */
export function stripLeadingHeading(markdown: string, researched: boolean): string {
    const match = /^\s*#{1,6}\s([^\n]*)(?:\n+|$)/.exec(markdown);
    if (!match || !(researched || /\?\s*$/.test(match[1]))) return markdown;
    return markdown.slice(match[0].length);
}
