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
const data=load('app/app/data.ts');
const {TodayView}=load('app/app/today.tsx');
const {SleeveView,SatelliteView}=load('app/app/portfolio/portfolio.tsx');
const {Missing,Header}=load('app/app/shared.tsx');
const q={close:110,sma200:100,distance_pct:10,price_as_of:'2026-10-16',stale:false};
const today={schema_version:1,as_of:'2026-10-16',breadth_source:'universe-1985-v1',market:{...q,light:'amber',spy_over_200d:true,breadth:.431,breadth_sample:290},signal_week:'2026-10-16',new_signals_this_week:8,orders_to_place:1,month_end:{rebalance_due:false,next_session:'2026-10-19',would_switch:['XLB']},stale:{},this_week:[]};
const sleeves=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY','SPY'].map(symbol=>({symbol,today:{...q,hold:symbol},month_end:{...q,hold:'SHY'},stale:false,would_switch:true}));
const portfolio={schema_version:1,as_of:'2026-10-16',status:'candidate',month_end_signal_as_of:'2026-09-30',sleeves};
const signals={schema_version:1,as_of:'2026-10-16',signals:[]};
const render=(C,props)=>renderToStaticMarkup(React.createElement(C,props));
test('all light states are words; counts, dates, source and empty tasks render',()=>{
  for(const [light,word] of [['green','绿灯'],['amber','黄灯'],['red','红灯'],[null,'暂无数据']]) {
    const html=render(TodayView,{data:{...today,market:{...today.market,light}}});
    const verdicts={green:'两个条件都满足：3W 可以挂新单。',amber:'两个条件只满足一个：按冻结规则，3W 这周不挂新单。',red:'两个条件都不满足：3W 不挂新单。'};
    if(light)assert.ok(html.includes(verdicts[light]));
    else assert.ok(!html.includes('3W 可以挂新单'));
    assert.ok(html.includes('43%'));assert.ok(html.includes('（过半才算好）'));
    assert.ok(html.includes('宽度有效样本数：290'));
    assert.ok(html.includes('<span>新信号</span>'));assert.ok(html.includes('<span>要挂的单</span>'));
    assert.ok(html.includes('有的信号不符合下单条件（比如大盘不好），所以要挂的单可能更少。'));
    assert.ok(html.includes(word)); assert.ok(html.includes('universe-1985-v1'));
    assert.ok(html.includes('本周没有要做的事'));assert.ok(html.includes('2026-10-16'));
    assert.match(html,/<strong>8<\/strong>/);assert.match(html,/<strong>1<\/strong>/);
  }
});
test('stale inputs retain actual dates, missing dates, rebalance and action labels',()=>{
  const html=render(TodayView,{data:{...today,stale:{'market.SPY':null,'sectors.XLB.today':'2026-10-15'},month_end:{...today.month_end,rebalance_due:true},this_week:[{kind:'new_order',symbol:'XLB'},{kind:'month_end_rebalance'}]}});
  for(const text of ['缺少报价','2026-10-15','已到月底调仓日','XLB · 挂限价单','部分输入数据滞后'])assert.ok(html.includes(text));
});
test('sleeves use month-end holding, equality is below, missing never becomes zero',()=>{
  assert.equal(data.trend({...q,close:100}),false);assert.equal(data.trend({...q,sma200:null}),null);
  const html=render(SleeveView,{data:portfolio});
  for(const text of ['候选组合','SHY','原材料','月底会换','Faber 2007'])assert.ok(html.includes(text));
  assert.equal((html.match(/Faber 2007/g)||[]).length,1);
  assert.ok(html.includes('本月持有：按 9 月 30 日收盘决定'));
  assert.ok(html.includes('按今天的价格，到月底会换成 XLB'));
  const switched=render(SleeveView,{data:{...portfolio,sleeves:[{...sleeves[0],today:{...q,close:90,distance_pct:-10.123,hold:'SHY'}}]}});
  assert.ok(switched.includes('按今天的价格，到月底会换成 SHY'));
  assert.ok(switched.includes('低于 200 日线'));assert.ok(switched.includes('-10.1%'));
  const missing=render(SleeveView,{data:{...portfolio,sleeves:[{...sleeves[0],today:{...q,close:null,sma200:null,distance_pct:null},month_end:{...q,hold:null},would_switch:null}]}});
  assert.ok(missing.includes('暂无数据'));assert.ok(!missing.includes('0.00%'));
});
test('satellite only counts open records and displays supplied distances without thresholds',()=>{
  const item={id:'a',symbol:'XLB',status:'open',quote:q,distances:{to_stop_pct:16.67,to_target_pct:33.33,to_stop_R:2,to_target_R:4}};
  const report={...signals,signals:[item,{...item,id:'b',status:'closed'}]};
  assert.equal(data.emptySlots(report),9);
  const html=render(SatelliteView,{data:report});
  for(const text of ['16.7%','33.3%','2.0R','4.0R','3w-1.9'])assert.ok(html.includes(text));
  assert.ok(render(SatelliteView,{data:signals}).includes('3W 目前没有持仓'));
  assert.equal(data.emptySlots({...signals,signals:Array(11).fill(item)}),0);
});
test('missing, failed, invalid JSON and malformed files resolve calmly',async()=>{
  const signal=new AbortController().signal;
  for(const fetcher of [async()=>({ok:false}),async()=>{throw Error('offline')},async()=>({ok:true,json:async()=>{throw Error('json')}}),async()=>({ok:true,json:async()=>({})})]) {
    assert.equal(await data.fetchReport('today',signal,fetcher),null);
  }
  const html=render(Missing,{});assert.ok(html.includes('数据还没生成'));assert.ok(html.includes('role="status"'));
  assert.ok(render(Missing,{loading:true}).includes('正在读取数据'));
});
test('only owned JSON endpoints requested and valid schema accepted',async()=>{
  for(const [kind,report] of Object.entries({today,portfolio,signals})) {
    let requested;
    const result=await data.fetchReport(kind,new AbortController().signal,async(url,opts)=>{requested=url;assert.equal(opts.cache,'no-store');return {ok:true,json:async()=>report}});
    assert.equal(requested,`/app/${kind}.json`);assert.equal(result,report);
    assert.equal(data.validReport(kind,{...report,schema_version:2}),false);
  }
  assert.equal(data.validReport('today',{...today,stale:null}),false);
  assert.equal(data.validReport('portfolio',{...portfolio,sleeves:[null]}),false);
  assert.equal(data.validReport('signals',{...signals,signals:[{}]}),false);
});
test('shared navigation exposes only two live links and three disabled tabs',()=>{
  const html=render(Header,{current:'portfolio'});
  assert.equal((html.match(/<a /g)||[]).length,2);assert.equal((html.match(/disabled=""/g)||[]).length,3);
  assert.ok(html.includes('aria-current="page"'));assert.ok(html.includes('即将上线'));
});
test('both new routes server-render in vinext without modifying existing routing',async()=>{
  const {default:worker}=await import('../dist/server/index.js');
  for(const route of ['/app','/app/portfolio']) {
    const response=await worker.fetch(new Request(`http://localhost${route}`,{headers:{accept:'text/html'}}),{ASSETS:{fetch:async()=>new Response('Not found',{status:404})}},{waitUntil(){},passThroughOnException(){}});
    assert.equal(response.status,200);
    const html=await response.text();assert.ok(html.includes('应用导航'));assert.ok(html.includes('正在读取数据'));assert.ok(html.includes('lang="zh-CN"'));
  }
});
