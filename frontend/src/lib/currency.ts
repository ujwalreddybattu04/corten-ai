/** Answers render `$...$` as inline math, so "**$340.97**, up **$31.55**" would be typeset as a formula.
 *  A `$` that starts an amount is escaped to stay text, unless it opens a short same-line span that is clearly
 *  a formula (such as `$2^{10}$`). Code spans and fenced blocks are left untouched. */
const FORMULA = /[\\^_{}=]/;
const WORDS = /\s[A-Za-z]{2,}\s/;

export function protectCurrency(markdown: string): string {
    return markdown.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map((part, index) => index % 2 ? part : part
        .replace(/(^|[^\\$])\$(?=\d)/g, (match: string, before: string, offset: number, whole: string) => {
            const rest = whole.slice(offset + before.length + 1);
            const close = rest.search(/(?<!\\)\$/);
            const line = rest.indexOf("\n");
            if (close !== -1 && (line === -1 || close < line)) {
                const span = rest.slice(0, close);
                if (FORMULA.test(span) && !WORDS.test(span)) return match;
            }
            return `${before}\\$`;
        })).join("");
}
