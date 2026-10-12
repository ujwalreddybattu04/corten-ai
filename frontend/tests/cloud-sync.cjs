const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const load = require('./load-ts');

function setup() {
    const cache = new Map(), values = new Map();
    global.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
    global.sessionStorage = { getItem: () => null };
    global.window = new EventTarget();
    global.document = Object.assign(new EventTarget(), { visibilityState: 'visible' });
    const storage = load(path.join(__dirname, '../src/lib/accountStorage.ts'), cache);
    const sync = load(path.join(__dirname, '../src/lib/cloudSync.ts'), cache);
    storage.setStorageAccount('owner-a');
    const records = new Map(); let revision = 0, offline = false;
    global.fetch = async (url, options) => {
        if (offline) throw new Error('Network unavailable');
        if (url.includes('/changes')) {
            const after = Number(new URL(url, 'https://example.com').searchParams.get('after'));
            return Response.json({ records: [...records.values()].filter(item => item.revision > after), cursor: revision, has_more: false });
        }
        return Response.json({ results: JSON.parse(options.body).records.map(item => {
            const key = `${item.namespace}:${item.id}`, previous = records.get(key);
            if (previous && previous.deleted === item.deleted && JSON.stringify(previous.data) === JSON.stringify(item.data)) return { ...previous, status: 'saved' };
            if ((previous?.revision || 0) !== item.expected_revision) return { namespace: item.namespace, id: item.id, status: 'conflict', current: previous || null };
            const result = { namespace: item.namespace, id: item.id, data: item.data, deleted: item.deleted, revision: ++revision };
            records.set(key, result); return { ...result, status: 'saved' };
        }) });
    };
    return { ...storage, ...sync, records, put(data, deleted = false) { const row = { namespace: 'threads', id: 'chat', data, deleted, revision: ++revision }; records.set('threads:chat', row); }, setOffline(value) { offline = value; } };
}

test('initial owned history uploads while guest histories stay separate', async () => {
    const s = setup();
    try {
        s.setStorageAccount(null); s.accountStorage.setItem('corten_threads', JSON.stringify([{ id: 'guest', title: 'Guest' }]));
        s.setStorageAccount('owner-a'); s.accountStorage.setItem('corten_threads', JSON.stringify([{ id: 'chat', title: 'Owned' }]));
        await s.startCloudSync('owner-a');
        assert.equal(s.records.get('threads:chat').data.title, 'Owned');
        assert.equal(s.records.has('threads:guest'), false);
        assert.equal(s.getCloudSyncStatus(), 'saved');
    } finally { s.stopCloudSync(); }
});

test('a fresh device restores remote history and later deletions remove its cache', async () => {
    const s = setup();
    try {
        s.put({ id: 'chat', title: 'Cloud history' }); await s.startCloudSync('owner-a');
        assert.equal(JSON.parse(s.accountStorage.getItem('corten_threads'))[0].title, 'Cloud history');
        s.put(null, true); await s.refreshCloudSync();
        assert.deepEqual(JSON.parse(s.accountStorage.getItem('corten_threads')), []);
    } finally { s.stopCloudSync(); }
});

test('offline edits persist and are uploaded after connection recovers', async () => {
    const s = setup();
    try {
        await s.startCloudSync('owner-a'); s.setOffline(true);
        s.accountStorage.setItem('corten_threads', JSON.stringify([{ id: 'chat', title: 'Offline work' }]));
        await s.refreshCloudSync(); assert.equal(s.getCloudSyncStatus(), 'offline');
        assert.equal(JSON.parse(s.accountStorage.getItem('corten_cloud_pending')).length, 1);
        s.setOffline(false); await s.refreshCloudSync();
        assert.equal(s.records.get('threads:chat').data.title, 'Offline work');
        assert.deepEqual(JSON.parse(s.accountStorage.getItem('corten_cloud_pending')), []);
    } finally { s.stopCloudSync(); }
});

test('concurrent device edits preserve both versions as visible records', async () => {
    const s = setup();
    try {
        s.put({ id: 'chat', title: 'Original' }); await s.startCloudSync('owner-a');
        s.accountStorage.setItem('corten_threads', JSON.stringify([{ id: 'chat', title: 'Local edit' }]));
        s.put({ id: 'chat', title: 'Remote edit' }); await s.refreshCloudSync();
        const rows = JSON.parse(s.accountStorage.getItem('corten_threads'));
        assert.equal(rows.length, 2);
        assert.ok(rows.some(row => row.title === 'Remote edit'));
        assert.ok(rows.some(row => row.title === 'Local edit (conflict copy)'));
        await s.refreshCloudSync();
        assert.equal(s.records.size, 2);
    } finally { s.stopCloudSync(); }
});

test('private mode never uploads private browser records', async () => {
    const s = setup(); global.sessionStorage = { getItem: () => 'true' };
    try {
        s.accountStorage.setItem('corten_threads', JSON.stringify([{ id: 'chat', title: 'Private' }]));
        await s.startCloudSync('owner-a'); assert.equal(s.records.size, 0);
    } finally { s.stopCloudSync(); }
});

test('private chat mode does not silently prevent saving independent Spaces', async () => {
    const s = setup(); global.sessionStorage = { getItem: () => 'true' };
    try {
        s.accountStorage.setItem('corten_spaces', JSON.stringify([{id:'space',name:'Research'}]));
        await s.startCloudSync('owner-a');
        assert.equal(s.records.get('spaces:space').data.name, 'Research');
        assert.equal(s.records.has('threads:chat'), false);
    } finally { s.stopCloudSync(); }
});

test('switching account during hydration cannot copy old-account data into the next account', async () => {
    const s = setup(); let release;
    global.fetch = () => new Promise(resolve => { release = resolve; });
    const initializing = s.startCloudSync('owner-a');
    s.stopCloudSync(); s.setStorageAccount('owner-b');
    release(Response.json({ records: [{ namespace: 'threads', id: 'chat', data: { id: 'chat', title: 'Secret A' }, revision: 1, deleted: false }], cursor: 1, has_more: false }));
    await initializing;
    assert.equal(s.accountStorage.getItem('corten_threads'), null);
});
