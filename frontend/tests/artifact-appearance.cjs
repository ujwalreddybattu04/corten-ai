const { test } = require("node:test");
const assert = require("node:assert/strict");
const load = require("./load-ts");
const { artifactAppearance } = load("src/lib/artifactAppearance.ts");
const { sandboxDocument, sandboxPermissions } = load("src/lib/artifacts.ts");
test("preview appearance preserves the artifact data, executable source and sandbox permissions", () => {
    for (const type of ["react", "html", "mermaid", "svg"]) {
        const source = type === "react" ? 'export default function App(){return <p>Price: 340.97 USD</p>}' : type === "mermaid" ? "graph TD;A-->B" : type === "svg" ? '<svg><text>340.97 USD</text></svg>' : '<html><HEAD><title>AAPL</title></HEAD><body style="background:white">340.97 USD<script>const values=[340.97,329.40];</script></body></html>';
        const original = sandboxDocument({ type, content: source });
        const themed = artifactAppearance(original);
        assert.equal(themed.replace(/<style id="corten-preview-appearance">[\s\S]*?<\/style>/, ""), original);
        assert.equal((themed.match(/<script/g) || []).length, (original.match(/<script/g) || []).length);
        assert.ok(!sandboxPermissions(type).includes("allow-same-origin"));
    }
});
