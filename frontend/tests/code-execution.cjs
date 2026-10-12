const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const load = require('./load-ts');
const original = global.fetch;
after(() => { global.fetch = original; });
const modulePath = path.join(__dirname, '../src/lib/codeExecution.ts');

test('code input rejects wrong types and oversized streamed requests', async () => {
    const { readExecutionInput } = load(modulePath);
    for (const body of [null, [], {language:4,code:'x'}, {language:'c',code:4}, {language:'c',code:'x',stdin:4}]) {
        await assert.rejects(readExecutionInput(new Request('https://example.com', {method:'POST',body:JSON.stringify(body)})));
    }
    await assert.rejects(readExecutionInput(new Request('https://example.com', {method:'POST',body:JSON.stringify({language:'c',code:'x'.repeat(400000)})})), /too large/);
    assert.deepEqual(await readExecutionInput(new Request('https://example.com', {method:'POST',body:JSON.stringify({language:'C',code:'int main(){}'})})), {language:'c',code:'int main(){}',stdin:''});
});

test('remote compiler selection uses available stable versions and coalesces catalogue requests', async () => {
    const { selectCompiler, supportedLanguage } = load(modulePath); let calls = 0;
    global.fetch = async () => { calls++; await new Promise(resolve => setTimeout(resolve,10)); return Response.json([{name:'gcc-head-c',language:'C'}, {name:'gcc-13.2.0-c',language:'C'}, {name:'gcc-9.0-c',language:'C'}, {name:'rust-1.82.0',language:'Rust'}]); };
    assert.deepEqual(await Promise.all([selectCompiler('c'),selectCompiler('rust')]), ['gcc-13.2.0-c','rust-1.82.0']);
    assert.equal(calls, 1);
    assert.equal(await selectCompiler('java'), null);
    assert.equal(supportedLanguage('kotlin'), false);
    assert.equal(supportedLanguage('constructor'), false);
});

test('a provider outage or malformed catalogue is recoverable rather than guessing a compiler', async () => {
    const { selectCompiler } = load(modulePath);
    global.fetch = async () => Response.json({detail:'failed'}, {status:503});
    await assert.rejects(selectCompiler('c'));
    global.fetch = async () => Response.json([{name:'gcc-13.2.0-c',language:'C'}]);
    assert.equal(await selectCompiler('c'), 'gcc-13.2.0-c');
});
