// Builds the self-hosted runtime that artifacts load inside their sandbox.
// Output is generated at build time (not committed) and served from /artifact-runtime/.
import { build } from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "artifact-runtime");
mkdirSync(out, { recursive: true });

await build({
    entryPoints: [join(root, "src", "artifact-runtime", "react-runtime.tsx")],
    outfile: join(out, "react-runtime.js"),
    bundle: true,
    minify: true,
    format: "iife",
    target: ["es2020"],
    legalComments: "none",
    define: { "process.env.NODE_ENV": '"production"' },
    logLevel: "warning",
});
copyFileSync(join(root, "node_modules", "mermaid", "dist", "mermaid.min.js"), join(out, "mermaid.min.js"));
console.log("Artifact runtime ready");
