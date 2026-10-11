const fs = require("node:fs");
const ts = require("typescript");
const Module = require("node:module");
const path = require("node:path");
module.exports = function loadTs(source, cache = new Map()) {
    source = path.resolve(source);
    if (cache.has(source)) return cache.get(source);
    const instance = new Module(source, module);
    instance.paths = Module._nodeModulePaths(path.dirname(source));
    const originalRequire = instance.require.bind(instance);
    instance.require = name => {
        if (name.startsWith("@/")) {
            const candidate = path.resolve(__dirname, "../src", name.slice(2)) + ".ts";
            if (fs.existsSync(candidate)) return loadTs(candidate, cache);
        }
        if (name.startsWith("./") || name.startsWith("../")) {
            const candidate = path.resolve(path.dirname(source), name) + ".ts";
            if (fs.existsSync(candidate)) return loadTs(candidate, cache);
        }
        return originalRequire(name);
    };
    instance._compile(ts.transpileModule(fs.readFileSync(source, "utf8"), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText, source);
    cache.set(source, instance.exports);
    return instance.exports;
};
