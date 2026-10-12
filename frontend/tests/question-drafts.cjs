const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const load = require('./load-ts');
function setup() {
    const cache = new Map(), values = new Map();
    global.window = { location: { search: '' } };
    global.sessionStorage = {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)};
    const account = load(path.join(__dirname,'../src/lib/accountStorage.ts'),cache);
    account.setStorageAccount('owner-a');
    const draft = load(path.join(__dirname,'../src/lib/questionDrafts.ts'),cache);
    return { ...account, ...draft, values };
}
test('international and long questions travel intact without being put into navigation URLs',()=>{
    const s=setup(), question='中文 forecast '.repeat(900);
    const route=s.questionPath(question,'academic','space-one');
    assert.ok(route.length<150);
    assert.equal(new URL(route,'https://example.com').searchParams.get('space'),'space-one');
    const id=new URL(route,'https://example.com').searchParams.get('draft');
    assert.equal(s.readQuestionDraft(id).query,question.trim());
    s.setStorageAccount('owner-b'); assert.equal(s.readQuestionDraft(id),null);
    s.setStorageAccount(null); assert.equal(s.readQuestionDraft(id),null);
});
test('private drafts stay private when the global toggle later changes',()=>{
    const s=setup();s.values.set('corten_private_mode','true');
    const route=s.questionPath('Private forecasting question');
    global.window.location.search=new URL(route,'https://example.com').search;
    s.values.set('corten_private_mode','false');
    assert.equal(s.privateQuestionDraft(),true);
});
test('blocked storage has a bounded fallback and invalid or expired drafts never generate a question',()=>{
    const s=setup();global.sessionStorage.setItem=()=>{throw new Error('blocked')};
    assert.match(s.questionPath('Small question'),/^\/search\?focus=all&q=/);
    assert.throws(()=>s.questionPath('中文'.repeat(2000)),/storage/);
    assert.throws(()=>s.questionPath('x'.repeat(17000)),/16,000/);
    assert.equal(s.readQuestionDraft('bad-id'),null);
    const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    s.values.set('corten_question_draft:'+id,JSON.stringify({owner:'owner-a',query:'Expired',created:Date.now()-86400001}));
    assert.equal(s.readQuestionDraft(id),null);
});

test('chat persistence fails closed when its privacy setting cannot be read',()=>{
    const s=setup();global.sessionStorage.getItem=()=>{throw new Error('blocked')};
    assert.equal(s.isPrivateChat(),true);
});
