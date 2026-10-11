const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const ts = require("typescript");
const Module = require("node:module");
const path = require("node:path");
const source = path.join(__dirname, "../src/lib/personalization.ts");
const compiled = ts.transpileModule(fs.readFileSync(source, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const { getWeightedFetchSizes } = require("./load-ts")(source);
const categories = ["technology", "business", "entertainment", "sports", "health"];

test("strong preferences preserve valid API sizes for every For You category", () => {
  for (const affinities of [
    { technology: 1000, sports: -100 },
    { business: 1000 },
    { entertainment: -1000, health: 500 },
  ]) {
    const sizes = getWeightedFetchSizes(categories, affinities, 50);
    assert.equal(Object.keys(sizes).length, categories.length);
    for (const size of Object.values(sizes)) {
      assert.ok(Number.isInteger(size) && size >= 6 && size <= 20);
    }
  }
});

test("new readers receive a balanced feed before any interaction history", () => {
  const sizes = getWeightedFetchSizes(categories, {}, 50);
  assert.deepEqual(Object.values(sizes), [10, 10, 10, 10, 10]);
});
