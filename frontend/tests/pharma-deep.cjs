const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const cache = new Map();
let owner = 'owner-a';
let privateMode = false;
let lastPost;
const validJob = { id: 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa', query: 'Research a drug', status: 'draft', plan: { topics: [] }, revision: 1, activity: [] };
cache.set(path.resolve('src/lib/api.ts'), { api: { post: async (url, body) => { lastPost = { url, body }; return validJob; } } });
cache.set(path.resolve('src/lib/accountStorage.ts'), { getStorageAccount: () => owner });
cache.set(path.resolve('src/lib/questionDrafts.ts'), { isPrivateChat: () => privateMode });
const deep = require('./load-ts')('src/lib/pharmaDeep.ts', cache);

test('Deep report sources accept forty explicit references and reject unsafe URLs', () => {
    const source = (id, url) => ({ id, url, title: 'Reference ' + id });
    const result = deep.deepSources([source(1, 'https://www.fda.gov/drugs/a'), source(40, 'https://www.ema.europa.eu/a'), source(41, 'https://www.fda.gov/a'), source(2, 'javascript:alert(1)'), source(3, 'https://user:password@www.fda.gov/a')]);
    assert.deepEqual(result.map(s => s.citationIndex), [1, 40]);
});

test('A research draft cannot leak from one signed-in account to another', () => {
    const storage = new Map();
    global.sessionStorage = { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
    deep.rememberDeepDraft('Investigate the original account question');
    owner = 'owner-b';
    assert.equal(deep.takeDeepDraft(), '');
    owner = 'owner-a';
    assert.equal(deep.takeDeepDraft(), 'Investigate the original account question');
    assert.equal(deep.takeDeepDraft(), '');
    delete global.sessionStorage;
});

test('Document methods keep full readings and search excerpts distinct', () => {
    assert.equal(deep.deepSourceMethod('search_excerpt'), 'Search excerpt');
    assert.equal(deep.deepSourceMethod('bounded_document'), 'Document read · limited');
    assert.equal(deep.deepSourceMethod('api_record'), 'Structured API record');
});

test('Only queued or running reports keep polling', () => {
    assert.equal(deep.deepActive(null), false);
    for (const status of ['queued', 'running', 'cancel_requested']) assert.equal(deep.deepActive({ status }), true);
    for (const status of ['draft', 'completed', 'partial', 'failed', 'cancelled']) assert.equal(deep.deepActive({ status }), false);
});

test('Malformed saved report responses fail with a readable reload action', () => {
    assert.throws(() => deep.checkDeepJob({ id: 'bad' }), /reload/);
    assert.throws(() => deep.checkDeepJob(null), /reload/);
});

test('Private research requires an explicit saved-report choice and preserves private chat mode', async () => {
    privateMode = true;
    await deep.prepareDeep('Investigate the trial evidence');
    assert.equal(lastPost.body.private, true);
    await deep.prepareDeep('Investigate the trial evidence', undefined, true);
    assert.equal(lastPost.body.private, false);
    assert.equal(privateMode, true);
    privateMode = false;
});
