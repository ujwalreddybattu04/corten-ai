/** Markdown with citations turned into in-page links: [1], 【1】 and 【1†source】 become chips that open the source.
 *  Code spans and fenced blocks are left untouched. */
export function linkCitations(markdown: string): string {
    return markdown.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map((part, index) => index % 2 ? part : part
        .replace(/【(\d{1,2}(?:\s*[,，]\s*\d{1,2})*)(?:†[^】\n]{0,80})?】/g, "[$1]")
        .replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\(|:)/g, (_, numbers: string) =>
            numbers.split(/\s*,\s*/).map(n => `[${n}](#cite-${n})`).join(""))).join("");
}
