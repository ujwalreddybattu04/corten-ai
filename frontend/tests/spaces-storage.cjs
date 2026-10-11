const assert = require("node:assert/strict");
const { test, after } = require("node:test");
const path = require("node:path");
const load = require("./load-ts");
const original = global.localStorage;
after(() => { global.localStorage = original; });

test("Space associations stay within the active account and do not duplicate threads", () => {
    const values = new Map();
    global.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
    const cache = new Map();
    const { accountStorage, setStorageAccount } = load(path.join(__dirname, "../src/lib/accountStorage.ts"), cache);
    const { associateSpaceThread } = load(path.join(__dirname, "../src/lib/spaces.ts"), cache);
    setStorageAccount("account-a");
    accountStorage.setItem("corten_spaces", JSON.stringify([{ id: "project", threadIds: [] }]));
    assert.equal(associateSpaceThread("project", "thread"), true);
    assert.equal(associateSpaceThread("project", "thread"), true);
    assert.deepEqual(JSON.parse(accountStorage.getItem("corten_spaces"))[0].threadIds, ["thread"]);
    setStorageAccount("account-b");
    assert.equal(accountStorage.getItem("corten_spaces"), null);
    assert.equal(associateSpaceThread("project", "other-thread"), false);
    setStorageAccount("account-a");
    assert.deepEqual(JSON.parse(accountStorage.getItem("corten_spaces"))[0].threadIds, ["thread"]);
});
test("all Space screens use account storage instead of global browser records", () => {
    const fs = require("node:fs");
    for (const file of ["page.tsx", "[id]/page.tsx", "templates/page.tsx"]) {
        const source = fs.readFileSync(path.join(__dirname, "../src/app/spaces", file), "utf8");
        assert.doesNotMatch(source, /localStorage\.(getItem|setItem)/);
    }
});
