/* eslint-disable @typescript-eslint/no-require-imports -- This local-only .cjs harness intentionally uses CommonJS. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={module:{exports:{}}};vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../work/v3w/daily1-src/stats.js'),'utf8'),context);const S=context.module.exports;
const items=Array.from({length:21},(_,i)=>({id:`${i}`,result:{r:i===0?0:i%2?2:-1}})),answers={};
for(let i=0;i<9;i++)answers[i]={choice:i%2?'do':'no',shape_wrong:i===0,confidence:i%3+1,note:'<script>',answered_at:new Date(1000*i).toISOString()};
assert.equal(S.batches(items,answers).length,0);
answers[9]={...answers[1],answered_at:new Date(9000).toISOString()};
let batch=S.batches(items,answers)[0];assert.equal(batch.correct,10);assert.equal(batch.do_r,2);assert.equal(batch.no_r,-.8);assert.equal(batch.all_r,.6);assert.equal(JSON.stringify(batch.wrong),JSON.stringify(['0']));
for(let i=10;i<21;i++)answers[i]={...answers[1],answered_at:new Date(1000*i).toISOString()};
assert.equal(JSON.stringify(S.batches(items,answers).map(x=>x.n)),JSON.stringify([10,10,1]));
assert.equal(S.mean([]),null);assert.equal(S.valid({...answers[0],confidence:4}),false);assert.equal(S.valid({...answers[0],choice:'bad'}),false);
console.log('daily trainer stats: passed');
