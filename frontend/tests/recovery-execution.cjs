const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const load = require('./load-ts');
const original = global.fetch;
after(() => { global.fetch = original; });
const file=path.join(__dirname,'../src/app/api/execute/route.ts');
function request(auth='') {
    const req=new Request('https://corten.example/api/v1/execute',{method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:auth}:{})},body:JSON.stringify({language:'c',code:'int main(){return 0;}'})});
    req.nextUrl=new URL(req.url);return req;
}
test('unsigned and forged execution requests cannot invoke the external compiler',async()=>{
    const execute=load(file);let calls=[];
    global.fetch=async url=>{calls.push(url);return Response.json({detail:'Invalid token'},{status:401});};
    assert.equal((await execute.POST(request())).status,401);assert.equal(calls.length,0);
    assert.equal((await execute.POST(request('Bearer forged'))).status,401);
    assert.ok(calls.every(url=>url.endsWith('/auth/me')));
});
test('session verification outages block execution without sending code',async()=>{
    const execute=load(file);let calls=0;
    global.fetch=async()=>{calls++;throw new Error('backend offline');};
    assert.equal((await execute.POST(request('Bearer signed'))).status,503);assert.equal(calls,1);
});
test('a verified session is checked before real compiler selection and execution',async()=>{
    const execute=load(file);let calls=[];
    global.fetch=async url=>{
        calls.push(url);
        if(url.endsWith('/auth/me'))return Response.json({id:'verified'});
        if(url.endsWith('/api/list.json'))return Response.json([{name:'gcc-13.2.0-c',language:'C'}]);
        return Response.json({status:'0',program_output:'OK'});
    };
    const response=await execute.POST(request('Bearer signed'));
    assert.equal(response.status,200);assert.equal((await response.json()).stdout,'OK');
    assert.ok(calls[0].endsWith('/auth/me'));assert.ok(calls.at(-1).endsWith('/api/compile.json'));
});
