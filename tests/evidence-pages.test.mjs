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
test('historical ticket shows checks, blocked gates, prices, dates and example replay',()=>{
 const html=render(TicketView,{ticket,chart:false});
 for(const text of ['历史示例','不计入真实前向信号','为什么触发','订单计划','冻结规则重算','2012-09-14','三推','底部'])assert.ok(html.includes(text),text);
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
const row={id:'test',symbol:'ABC',signal_week:'2026-10-02',status:'closed',moves:{'1w':{date:'2026-10-09',move_pct:10},'4w':null,'13w':null},outcome:'target',R:3,exit_date:'2026-10-16',random:{twins:'verified',sampled:30,closed:20,median_R:-1,beat_share:.75,mean_R:0},gross_R:3.02,alert_id:'A-abcdef',lifecycle:{status:'target',date:'2026-10-16'}};
test('forward empty state, verified and mismatched twins, scoring rule and own scroll region',()=>{
 const html=render(ForwardView,{data:{...forward,signals:[],summary:{...forward.summary,signals:0}}});
 for(const text of ['还没有真实前向信号','下次检查：周五收盘后','继续记录，未证明','需模拟账户，不在公开页','已结束 / 下一检查点','287','0.44R'])assert.ok(html.includes(text),text);
 const report={...forward,signals:[row],cumulative_R:[{date:'2026-10-16',R:3}],summary:{signals:1,closed:1,average_R:3,win_rate:1,beat_random_share:.75,beat_random_signals:1}};
 assert.ok(data.validForward(report));
 const active=render(ForwardView,{data:report});
 for(const text of ['75.00%','-1.00R','10.00%','20/30','tabindex="0"'])assert.ok(active.includes(text),text);
 report.signals=[{...row,random:{...row.random,twins:'unverified',median_R:null,beat_share:null,mean_R:null}}];
 const missing=render(ForwardView,{data:report});assert.ok(missing.includes('未核验'));assert.ok(!missing.includes('盲判'));assert.ok(!missing.includes('-1.00R'));
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

test('ticket prioritizes full-width chart, five checks, order/outcome, then collapsed details',()=>{
 const html=render(TicketView,{ticket});
 const positions=['svTicketHead','svEvidenceFigure','svKeyChecks','svTicketColumns','svAllChecks'].map(x=>html.indexOf(x));
 assert.ok(positions.every((p,i)=>p>=0&&(!i||p>positions[i-1])));
 assert.equal((html.split('svKeyChecks')[1].split('</section>')[0].match(/<li/g)||[]).length,5);
 assert.ok(html.includes('<summary>全部 26 条</summary>'));assert.doesNotMatch(html,/<details[^>]*open/);
 assert.ok(html.includes(ticket.outcome.fill_date));assert.ok(html.includes(ticket.outcome.exit_date));assert.ok(html.includes('-1.00R'));
 const {shapeRange,futureWeeks}=load('app/evidence/chart.tsx');
 const range=shapeRange(ticket);
 assert.equal(range.from,ticket.weekly.findIndex(b=>b.date===ticket.pushes[0].date)-8);
 assert.equal(range.to,ticket.weekly.findIndex(b=>b.date===ticket.signal_week)+12);
 assert.equal(futureWeeks(ticket.signal_week).length,12);
 assert.ok(futureWeeks(ticket.signal_week).every(b=>Object.keys(b).join()==='time'));
 const css=fs.readFileSync('app/evidence/style.css','utf8');assert.ok(css.includes('height:420px'));assert.ok(css.includes('height:300px'));
});

 test('next check uses record date and always advances to the next Friday',()=>{
 const {nextFriday}=load('app/forward/forward.tsx');
 for(const [date,expected] of [['2026-10-18T09:10:48Z','10-23'],['2026-10-23','10-30'],['2026-12-31','01-01']])assert.equal(nextFriday(date),expected);
 // Exercise this date and empty state independently of the daily published record.
 const datedForward={...forward,outcomes_as_of:'2026-10-18T09:10:48Z',summary:{...forward.summary,signals:0}};
 const html=render(ForwardView,{data:datedForward});assert.ok(html.includes('10-23'));assert.ok(html.includes('svForwardSample'));
 const {ForwardSummary}=load('app/app/today.tsx');
 const summary=render(ForwardSummary,{data:datedForward});assert.ok(summary.includes('href="/forward"'));assert.ok(summary.includes('2026-10-18'));
 assert.doesNotMatch(render(ForwardSummary,{data:datedForward},'en'),/[\u3400-\u9fff]/);
 });

test('ticket uses six order fields and one four-stage outcome without body credit',()=>{
 const html=render(TicketView,{ticket});
 const order=html.split('<dl class="svOrder">')[1].split('</dl>')[0];
 assert.equal((order.match(/<dt>/g)||[]).length,6);
 const timeline=html.split('<ol class="svOutcomeSteps"')[1].split('</ol>')[0];
 assert.equal((timeline.match(/<li /g)||[]).length,4);
 assert.equal((html.match(/-1.00R/g)||[]).length,1);
 assert.ok(!html.includes('TradingView Lightweight Charts'));
 assert.ok(fs.readFileSync('app/site-footer.tsx','utf8').includes('https://www.tradingview.com/'));
});

 test('stepper distinguishes waiting, open, terminal and unverified outcomes',()=>{
 const {OutcomeStepper}=load('app/evidence/stepper.tsx');
 const base={signalDate:'2026-10-02',fillDate:'2026-10-05',exitDate:'2026-10-16',fillPrice:10,exitPrice:13,R:3};
 for(const [status,done,current] of [['waiting',1,1],['open',2,1],['filled',2,1],['closed',4,1],['cancelled',1,0],['skipped',1,0],['unverified',1,0]]){
  const html=render(OutcomeStepper,{...base,status});
  assert.equal((html.match(/class="isDone/g)||[]).length,done,status);
  assert.equal((html.match(/aria-current="step"/g)||[]).length,current,status);
  assert.equal((html.match(/<svg/g)||[]).length,4);
  if(status!=='closed'){assert.ok(html.includes('data-result="neutral"'));assert.ok(!html.includes('3.00R'));assert.ok(!html.includes('2026-10-16'));}
 }
 const {stepIcons}=load('app/site-icon.tsx');
 for(const [outcome,R,colour,icon] of [['win',3,'positive','target'],['loss',-1,'negative','stop'],['time',.5,'positive','time'],['time',-.5,'negative','time'],['time',0,'neutral','time']]){
  const props={...base,status:'closed',outcome,R};const html=render(OutcomeStepper,props);
  assert.ok(html.includes(`data-result="${colour}"`));assert.ok(html.includes(`d="${stepIcons[icon]}"`));
  const mini=render(OutcomeStepper,{...props,mini:true});assert.ok(mini.includes('isMini'));assert.ok(!mini.includes('<time>'));assert.ok(!mini.includes('<strong>'));assert.equal((mini.match(/<svg/g)||[]).length,4);
  assert.doesNotMatch(render(OutcomeStepper,props,'en'),/[\u3400-\u9fff]/);
 }
 const report={...forward,signals:[row]};assert.ok(render(ForwardView,{data:report}).includes('svStepperScroll isMini'));
 const unknown=render(OutcomeStepper,{status:'filled',signalDate:'2026-10-02',R:null});assert.ok(!unknown.includes('NaN'));assert.ok(unknown.includes('—'));
 });

test('judging schema, missing scorecard and all reached checkpoints are bilingual',()=>{
 const missing={...forward,judging:{...forward.judging,status:'missing',completed:null,scored:null,unscorable:null,next_checkpoint:null,to_go:null,alarm1:null,verdict:'本次运行未生成计分'}};
 assert.ok(data.validForward(missing));assert.ok(render(ForwardView,{data:missing}).includes('本次运行未生成计分'));
 assert.doesNotMatch(render(ForwardView,{data:missing},'en'),/[\u3400-\u9fff]/);
 const checkpoints=[30,60,100].map(k=>({k,scored:k,unscorable:0,mean_d:-.5,t:-2.1,alarm1:true,verdict:'失效警报1'}));
 const reached={...forward,judging:{...forward.judging,completed:101,scored:101,unscorable:0,next_checkpoint:200,to_go:99,alarm1:true,verdict:'失效警报1',checkpoints}};
 assert.ok(data.validForward(reached));assert.ok(render(ForwardView,{data:reached}).includes('-2.10'));
 assert.doesNotMatch(render(ForwardView,{data:reached},'en'),/[\u3400-\u9fff]/);
 for(const bad of [{...reached.judging,to_go:100},{...reached.judging,checkpoints:checkpoints.slice(1)},{...forward.judging,completed:-1},{...forward.judging,alarm1:null},{...forward.judging,thresholds:{...forward.judging.thresholds,proof_t_gte:1}}])assert.equal(data.validForward({...forward,judging:bad}),false);
 assert.equal(data.validForward({...forward,judging:null}),false);
 assert.equal(data.validForward({...forward,signals:[{...row,blind:{choice:'do'}}]}),false);
});

test('executable forward summary is separate and absent values show unavailable',()=>{
 const empty=render(ForwardView,{data:{...forward,executable:null}});
 assert.ok(empty.includes('实际能做到（信号认出后才挂单）'));assert.ok(empty.includes('暂无'));
 const executable={computed_at:'2026-10-29T08:00:00Z',trades:7,wins:3,mean_R:.262,sum_R:1.834,skipped_stop:1,skipped_target:1,waiting:2,open:1};
 const active={...forward,executable};assert.ok(data.validForward(active));
 const html=render(ForwardView,{data:active});assert.ok(html.includes('0.26R'));
 assert.doesNotMatch(render(ForwardView,{data:active},'en'),/[\u3400-\u9fff]/);
 assert.equal(data.validForward({...active,executable:{...executable,mean_R:'bad'}}),false);
});
