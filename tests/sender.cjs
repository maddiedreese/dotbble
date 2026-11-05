const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createHmac, randomBytes } = require('node:crypto');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../build');
const coreContext = {};
vm.runInNewContext(fs.readFileSync(path.join(root, 'core.test-bundle.js'), 'utf8'), coreContext);
const core = coreContext.RingDotCore;
function config() {
  return {version:1,event:'ring.message',id:'sub_test',url:'https://api.openai.com/test-placeholder',
    device_id:'a'.repeat(32),secret:'whsec_'+Buffer.alloc(32,19).toString('base64'),expires:Date.now()+1800000};
}
function boot(store=new Map(), transport=async()=>({status:200}), clock=Date) {
  const handlers={}; const sent=[];
  vm.runInNewContext(fs.readFileSync(path.join(root,'plugin.js'),'utf8'), {
    Date:clock,
    localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},
    fetch:async(url,request)=>{sent.push({url,request});return transport(url,request);},
    Pebble:{registerSourceHandler:fn=>handlers.source=fn,registerActionHandler:fn=>handlers.action=fn,
      registerConfigHandler:fn=>handlers.config=fn,refreshSources:()=>{}}
  });
  async function call(kind,request){
    let result;
    const capture=v=>{assert.equal(result,undefined);result=JSON.parse(JSON.stringify(v));};
    await handlers[kind](request,kind==='config'?capture:{data:capture,ok:v=>capture({ok:true,...v}),error:(code,message)=>capture({ok:false,code,message})});
    assert.notEqual(result,undefined); return result;
  }
  return {call,store,sent};
}
test('UTF-8 matches native encoding without TextEncoder, including lone surrogates',()=>{
  for(const text of ['', 'Café 🪁\n中文', '\ud800', '\udc00', '\ud800x', 'a'.repeat(8000)]) {
    assert.deepEqual(Array.from(core.utf8(text)),Array.from(Buffer.from(text)));
  }
});
test('Standard Webhooks signatures match Node HMAC across permitted key sizes',()=>{
  for(let size=24;size<=64;size++){
    const cfg=config(), key=randomBytes(size);cfg.secret='whsec_'+key.toString('base64');
    const now=Date.now(), body=core.eventBody('Café 🪁 "kite"\n你好',cfg,1,now);
    const req=core.signedRequest(cfg,body,now);
    const h=req.headers,expected=createHmac('sha256',key).update(h['webhook-id']+'.'+h['webhook-timestamp']+'.'+body).digest('base64');
    assert.equal(h['webhook-signature'],'v1,'+expected);
    assert.equal(req.body,body);
  }
});
test('rejects expired pairings, malformed keys and non-OpenAI callback destinations',()=>{
  for(const url of ['http://api.openai.com/x','https://openai.com.evil.example/x','https://evil.example/openai.com','https://user@api.openai.com/x','https://api.openai.com:444/x','https://api.openai.com/x#secret','https://127.0.0.1/x']){
    assert.throws(()=>core.validateConfig({...config(),url}));
  }
  assert.throws(()=>core.validateConfig({...config(),expires:Date.now()-1}));
  assert.throws(()=>core.validateConfig({...config(),expires:Date.now()+7200000}));
  assert.throws(()=>core.validateConfig({...config(),secret:'whsec_not-base64!'}));
});
test('unpaired sender makes no request; pairing status never exposes the credential',async()=>{
  const {call,sent}=boot();
  assert.equal((await call('action',{action:'create_note',args:{text:'test'}})).ok,false);
  assert.equal(sent.length,0);
  const cfg=config(),paired=await call('config',{type:'pair',pairing:JSON.stringify(cfg)});
  assert.equal(paired.ready,true); assert(!JSON.stringify(paired).includes(cfg.secret));
});
test('every new send includes the preamble and unmodified transcript; state survives restart',async()=>{
  const {call,store,sent}=boot();await call('config',{type:'pair',pairing:JSON.stringify(config())});
  const text='Write a two-sentence story about a kite. 🪁';
  assert.equal((await call('action',{action:'create_note',args:{text}})).ok,true);
  assert.equal(sent.length,1); assert.equal(JSON.parse(sent[0].request.body).data.text,core.MESSAGE_PREAMBLE+text);
  const result=await boot(store).call('config',{type:'status'});
  assert.equal(result.count,1);assert.equal(result.pending,false);
  assert.equal(result.version,'1.0.0');assert.equal(result.instructionMode,'per-message');
  assert(!store.get('ring_dot_direct_test_v1').includes(text));
  const restarted=boot(store);
  const second='Write another haiku.\nKeep this line. 🪁';
  assert.equal((await restarted.call('action',{action:'create_note',args:{text:second}})).ok,true);
  assert.equal(JSON.parse(restarted.sent[0].request.body).data.text,core.MESSAGE_PREAMBLE+second);
  assert.notEqual(JSON.parse(sent[0].request.body).eventId,JSON.parse(restarted.sent[0].request.body).eventId);
});
test('unconfirmed delivery is persisted and retries reuse event identity and exact body',async()=>{
  const first=boot(new Map(),async()=>{throw new Error('network error with private URL');});
  await first.call('config',{type:'pair',pairing:JSON.stringify(config())});
  const failure=await first.call('action',{action:'create_note',args:{text:'hello'}});
  assert.equal(failure.ok,false);assert(!failure.message.includes('private URL'));
  const next=boot(first.store);
  assert.equal((await next.call('action',{action:'create_note',args:{text:'another'}})).ok,false);
  assert.equal(next.sent.length,0);
  assert.equal((await next.call('config',{type:'retry'})).pending,false);
  assert.equal(next.sent[0].request.body,first.sent[0].request.body);
});
test('expired and disconnected connections cannot send; gone callback clears the key',async()=>{
  const gone=boot(new Map(),async()=>({status:410}));
  await gone.call('config',{type:'pair',pairing:JSON.stringify(config())});
  assert.equal((await gone.call('action',{action:'create_note',args:{text:'hello'}})).ok,false);
  assert.equal((await gone.call('config',{type:'status'})).ready,false);
  assert(!gone.store.get('ring_dot_direct_test_v1').includes('whsec_'));
  await gone.call('config',{type:'disconnect'});assert.equal(gone.store.size,0);
});
test('ten-message limit is enforced without generating random IDs on the phone',async()=>{
  const {call,sent}=boot();await call('config',{type:'pair',pairing:JSON.stringify(config())});
  for(let i=0;i<10;i++)assert.equal((await call('action',{action:'create_note',args:{text:'test '+i}})).ok,true);
  assert.equal((await call('action',{action:'create_note',args:{text:'eleventh'}})).ok,false);
  assert.equal(new Set(sent.map(s=>s.request.headers['webhook-id'])).size,10);
});

test('diagnostics persist the pre-fetch stages while delivery is waiting, without private data',async()=>{
  let release;
  const response=new Promise(resolve=>{release=resolve;});
  const app=boot(new Map(),()=>response);
  const cfg=config();
  await app.call('config',{type:'pair',pairing:JSON.stringify(cfg)});
  const action=app.call('action',{action:'create_note',args:{text:'PRIVATE TRANSCRIPT'}});
  const waiting=JSON.parse(app.store.get('ring_dot_direct_trace_v1'));
  assert.deepEqual(waiting.map(x=>x.stage),['action-start','message-queued','signing-start','request-start']);
  for(const row of waiting) assert(Number.isFinite(Date.parse(row.at)));
  release({status:200});
  assert.equal((await action).ok,true);
  const status=await boot(app.store).call('config',{type:'status'});
  assert.deepEqual(status.diagnostics.slice(-2).map(x=>x.stage),['http-response','action-complete']);
  assert.equal(status.diagnostics.at(-2).httpStatus,200);
  for(const secret of ['PRIVATE TRANSCRIPT',cfg.url,cfg.secret]) assert(!JSON.stringify(status).includes(secret));
});
test('diagnostics are bounded and never retain transport exception details',async()=>{
  const app=boot(new Map(),async()=>{throw new Error('SECRET TRANSPORT URL');});
  await app.call('config',{type:'pair',pairing:JSON.stringify(config())});
  for(let i=0;i<30;i++) await app.call('action',{action:'create_note',args:{text:'PRIVATE TEXT'}});
  const rows=JSON.parse(app.store.get('ring_dot_direct_trace_v1'));
  assert.equal(rows.length,40);
  assert(!JSON.stringify(rows).includes('SECRET'));
  assert(!JSON.stringify(rows).includes('PRIVATE'));
  await app.call('config',{type:'disconnect'});
  assert.equal(app.store.size,0);
});

test('lasting configuration requires explicit version 2 and null expiry; legacy expiry stays enforced',()=>{
  assert.throws(()=>core.validateConfig({...config(),expires:null}));
  assert.throws(()=>core.validateConfig({...config(),version:2}));
  assert.throws(()=>core.validateConfig({...config(),version:2,expires:undefined}));
  const durable={...config(),version:2,expires:null};
  assert.equal(core.validateConfig(durable,Date.now()+90*86400000).version,2);
  assert.throws(()=>core.validateConfig(config(),Date.now()+90*86400000));
});
test('non-expiring pairing sends after 90 days and restart, beyond ten messages, preserving unique IDs',async()=>{
  const app=boot();const cfg={...config(),version:2,expires:null};
  await app.call('config',{type:'pair',pairing:JSON.stringify(cfg)});
  for(let i=0;i<12;i++)assert.equal((await app.call('action',{action:'create_note',args:{text:'test '+i}})).ok,true);
  const future=Date.now()+90*86400000;
  class FutureDate extends Date {constructor(...args){super(...(args.length?args:[future]));}static now(){return future;}}
  const restarted=boot(app.store,async()=>({status:200}),FutureDate);
  const status=await restarted.call('config',{type:'status'});
  assert.equal(status.ready,true);assert.equal(status.pairingMode,'non-expiring');assert.equal(status.expires,null);
  assert.equal((await restarted.call('action',{action:'create_note',args:{text:'after restart'}})).ok,true);
  const ids=[...app.sent,...restarted.sent].map(s=>s.request.headers['webhook-id']);
  assert.equal(new Set(ids).size,13);
  assert.equal(restarted.sent[0].request.headers['webhook-timestamp'],String(Math.floor(future/1000)));
  const revoked=boot(app.store,async()=>({status:410}),FutureDate);
  assert.equal((await revoked.call('action',{action:'create_note',args:{text:'revoked'}})).ok,false);
  assert.equal((await revoked.call('config',{type:'status'})).ready,false);
  assert(!app.store.get('ring_dot_direct_test_v1').includes(cfg.secret));
});
