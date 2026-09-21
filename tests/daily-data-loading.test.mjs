import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const compiled=ts.transpileModule(fs.readFileSync('app/zh/watch/market/daily-data.ts','utf8'),{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText;
function browser(fetcher){
 const states=[],effects=[],intervals=[],listeners={};
 const compiledModule={exports:{}};
 vm.runInNewContext(compiled,{
  module:compiledModule,exports:compiledModule.exports,AbortController,AbortSignal:{},setTimeout,clearTimeout,
  fetch:fetcher,
  require:()=>({useCallback:f=>f,useEffect:f=>effects.push(f),useState:value=>{
   const i=states.length;states.push(value);return [value,next=>{states[i]=next}];
  }}),
  setInterval:f=>{intervals.push(f);return 1},clearInterval:()=>{},
  document:{visibilityState:'visible',addEventListener:(key,f)=>{listeners[key]=f},removeEventListener:key=>{delete listeners[key]}},
 });
 return {...compiledModule.exports,states,effects,intervals,listeners};
}
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const response=data=>({ok:true,json:async()=>data});
const paths=['/update-status.json','/market-cockpit.json','/industry-radar.json'];

test('Market and Industry load real saved assets without modern AbortSignal statics',async()=>{
 const requests=[];
 const env=browser(async(path,options)=>{
  requests.push(path);assert.equal(options.cache,'no-store');assert.equal(options.signal.aborted,false);
  return response(JSON.parse(fs.readFileSync(`public${path}`,'utf8')));
 });
 env.useDailyData(paths);const cleanup=env.effects[0]();await tick();
 assert.equal(requests.length,3);assert.equal(env.states[1],false);
 const date=env.states[0][paths[0]].source_latest_complete_date;
 assert.ok(date);assert.equal(env.states[0][paths[1]].as_of,date);assert.equal(env.states[0][paths[2]].as_of,date);
 await env.intervals[0]();await tick();assert.equal(requests.length,6);cleanup();
});

test('one failed asset stays isolated and recovers on refresh',async()=>{
 let broken=true;
 const env=browser(async path=>path===paths[1]&&broken?{ok:false}:response({as_of:'2026-09-18'}));
 env.useDailyData(paths);const cleanup=env.effects[0]();await tick();
 assert.equal(env.states[0][paths[1]],null);assert.ok(env.states[0][paths[0]]);assert.ok(env.states[0][paths[2]]);
 broken=false;await env.intervals[0]();await tick();assert.ok(env.states[0][paths[1]]);cleanup();
});

function pendingFetch(_path,{signal}){
 return new Promise((_,reject)=>{
  if(signal.aborted)return reject(new Error('aborted'));
  signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});
 });
}
test('timeouts abort stalled requests without AbortSignal.timeout',async()=>{
 const env=browser(pendingFetch);
 await assert.rejects(env.fetchDailyAsset('/slow',new AbortController().signal,5),/aborted/);
});
test('unmount cancels pending requests and never writes stale reports',async()=>{
 const env=browser(pendingFetch);env.useDailyData(paths);
 const cleanup=env.effects[0]();cleanup();await tick();
 assert.equal(Object.keys(env.states[0]).length,0);assert.equal(env.states[1],true);
});
test('an already cancelled load aborts and a later independent load succeeds',async()=>{
 const env=browser(pendingFetch),parent=new AbortController();parent.abort();
 await assert.rejects(env.fetchDailyAsset('/cancelled',parent.signal),/aborted/);
 const next=browser(async()=>response({ok:true}));
 assert.deepEqual(await next.fetchDailyAsset('/new',new AbortController().signal),{ok:true});
});
