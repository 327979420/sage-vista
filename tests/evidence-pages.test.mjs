import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),cache=new Map();
function load(file) {
  file=path.resolve(file);
  if(cache.has(file))return cache.get(file).exports;
  const mod={exports:{}};cache.set(file,mod);
  const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  vm.runInNewContext(code,{module:mod,exports:mod.exports,AbortController,setTimeout,clearTimeout,require:name=>{
    if(!name.startsWith('.'))return require(name);
    const base=path.resolve(path.dirname(file),name);
    return load(['.ts','.tsx'].map(ext=>base+ext).find(p=>fs.existsSync(p)));
  }});
  return mod.exports;
}
const {LocaleProvider}=load('app/i18n/locale.tsx');
const data=load('app/evidence/data.ts');
const {TicketView,checkValue}=load('app/evidence/ticket.tsx');
const {TicketList}=load('app/signals/signals.tsx');
const {ForwardView,CumulativeChart}=load('app/forward/forward.tsx');
const {EvidenceHeader}=load('app/evidence/shared.tsx');
const ticket=JSON.parse(fs.readFileSync('public/app/ticket-example.json'));
const forward=JSON.parse(fs.readFileSync('public/app/forward.json'));
const render=(C,props,locale='zh')=>renderToStaticMarkup(React.createElement(LocaleProvider,{initialLocale:locale},React.createElement(C,props)));
test('owned artifacts validate; malformed and failed requests resolve to missing',async()=>{
 assert.ok(data.validTicket(ticket));assert.ok(data.validForward(forward));assert.ok(data.validIndex([]));
 for(const value of [null,{}, {...ticket,weekly:[]},{...ticket,order:null},{...ticket,id:'../bad'}])assert.equal(data.validTicket(value),false);
 for(const value of [null,{}, {...forward,summary:null},{...forward,cumulative_R:[null]}])assert.equal(data.validForward(value),false);
 for(const fetcher of [async()=>({ok:false}),async()=>{throw Error('offline')},async()=>({ok:true,json:async()=>({})})])assert.equal(await data.fetchEvidence('/app/forward.json',data.validForward,new AbortController().signal,fetcher),null);
});
test('historical ticket shows checks, blocked gates, prices, dates and unverified outcome',()=>{
 const html=render(TicketView,{ticket,chart:false});
 for(const text of ['历史示例','不计入真实前向信号','为什么触发','订单计划','未核验','2012-09-14','三推','底部'])assert.ok(html.includes(text),text);
 assert.ok(!html.includes('undefined'));assert.ok(!html.includes('[object Object]'));
 const blocked=structuredClone(ticket);blocked.checks[0].pass=false;blocked.order.eligible=false;
 assert.ok(render(TicketView,{ticket:blocked,chart:false}).includes('不满足挂单条件'));
 assert.ok(render(TicketView,{ticket:blocked,chart:false}).includes('aria-label="未通过"'));
 assert.equal(checkValue({id:'breadth_over_half',value:{fraction:null,sample_size:null}}),'—% · n=—');
});
test('index is newest first and does not mutate the input',()=>{
 const rows=[{id:'old',symbol:'A',signal_week:'2026-10-02',status:'closed',R:3},{id:'new',symbol:'B',signal_week:'2026-10-16',status:'waiting',R:null}];
 assert.equal(data.orderedTickets(rows)[0].id,'new');assert.equal(rows[0].id,'old');
 const html=render(TicketList,{rows,selected:'new',onSelect(){}});
 assert.ok(html.indexOf('2026-10-16')<html.indexOf('2026-10-02'));assert.ok(html.includes('aria-pressed="true"'));
});
const row={id:'test',symbol:'ABC',signal_week:'2026-10-02',status:'closed',moves:{'1w':{date:'2026-10-09',move_pct:10},'4w':null,'13w':null},outcome:'target',R:3,exit_date:'2026-10-16',random:{twins:'verified',sampled:30,closed:20,median_R:-1,beat_share:.75,mean_R:0},blind:{choice:'do',score:'right',judged_at:null,judged_after_fill:false}};
test('forward empty state, verified and mismatched twins, scoring rule and own scroll region',()=>{
 const html=render(ForwardView,{data:forward});
 for(const text of ['还没有真实前向信号','每周五收盘后','未成交或仍持仓','287','0.44R'])assert.ok(html.includes(text),text);
 const report={...forward,signals:[row],cumulative_R:[{date:'2026-10-16',R:3}],summary:{signals:1,closed:1,average_R:3,win_rate:1,beat_random_share:.75,beat_random_signals:1}};
 assert.ok(data.validForward(report));
 const active=render(ForwardView,{data:report});
 for(const text of ['75.00%','-1.00R','10.00%','20/30','tabindex="0"'])assert.ok(active.includes(text),text);
 report.signals=[{...row,random:{...row.random,twins:'unverified',median_R:null,beat_share:null,mean_R:null},blind:{...row.blind,score:'not yet scored'}}];
 const missing=render(ForwardView,{data:report});assert.ok(missing.includes('未核验'));assert.ok(missing.includes('尚未计分'));assert.ok(!missing.includes('-1.00R'));
 const curve=render(CumulativeChart,{points:[{date:'2026-10-01',R:1},{date:'2026-10-02',R:2},{date:'2026-10-11',R:3}]});assert.ok(curve.includes('L94,'),'date spacing, not equal point spacing');
});
test('evidence content follows the existing language toggle',()=>{
 for(const [C,props] of [[TicketView,{ticket,chart:false}],[ForwardView,{data:forward}],[ForwardView,{data:{...forward,signals:[row]}}],[EvidenceHeader,{}],[EvidenceHeader,{forward:true}]])assert.doesNotMatch(render(C,props,'en'),/[\u3400-\u9fff]/,C.name);
});
test('evidence routes and previous aliases render without coming-soon placeholders',async()=>{
 const {default:worker}=await import('../dist/server/index.js');
 for(const route of ['/signals','/forward','/opportunities','/scorecard']){
  const response=await worker.fetch(new Request(`http://localhost${route}`,{headers:{accept:'text/html',cookie:'sv-language-session=zh'}}),{ASSETS:{fetch:async()=>new Response('Not found',{status:404})}},{waitUntil(){},passThroughOnException(){}});
  assert.equal(response.status,200);const html=await response.text();assert.ok(html.includes('正在读取数据'));assert.ok(!html.includes('即将上线'));assert.ok(html.includes('href="/signals"'));assert.ok(html.includes('href="/forward"'));
 }
});

test('chart crosshair dates accept the library BusinessDay event format',()=>{
 const {chartDate}=load('app/evidence/chart.tsx');
 assert.equal(chartDate({year:2012,month:9,day:14}),'2012-09-14');
 assert.equal(chartDate('2012-09-14'),'2012-09-14');assert.equal(chartDate(undefined),undefined);
});
