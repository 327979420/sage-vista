import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url);
const source=fs.readFileSync(new URL('../app/zh/watch/resonance/rare-opportunities/cr056-ranking.tsx',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const compiledModule={exports:{}};
const contextSource=fs.readFileSync(new URL('../app/zh/watch/industry-radar/context.tsx',import.meta.url),'utf8');
const contextCode=ts.transpileModule(contextSource,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const contextModule={exports:{}};
new Function('require','exports','module',contextCode)(require,contextModule.exports,contextModule);
new Function('require','exports','module',compiled)(id=>id==='../../industry-radar/context'?contextModule.exports:require(id),compiledModule.exports,compiledModule);
const data=JSON.parse(fs.readFileSync(new URL('../public/cr056-ranking.json',import.meta.url),'utf8'));

test('real candidate projection renders its date, same backend scores and daily-update boundary',()=>{
 const html=renderToStaticMarkup(React.createElement(compiledModule.exports.CandidateView,{data,latestDate:new Date(Date.parse(data.as_of+'T00:00:00Z')+7*86400000).toISOString().slice(0,10)}));
 assert.match(html,data.automatic_updates_connected?/随现有日终流程自动复评/:/新榜自动日更尚未接通/);
 assert.match(html,/更新落后/);
 assert.ok(html.includes(data.as_of));
 const first=data.reviews.find(r=>r.symbol===data.ranked_symbols[0]);
 if(first){assert.ok(html.includes(first.symbol));assert.ok(html.includes(first.total.toFixed(2)));}
 assert.match(html,/新提名/);assert.ok(html.includes(`${data.new_nomination_symbols.length}只`));
 assert.match(html,/尚未验证收益/);
 if(first){assert.ok(html.includes(first.periods.monthly));assert.ok(html.includes(first.periods.weekly));}
 assert.doesNotMatch(html,/API_TOKEN|adjusted_close/);
});
test('an empty computed list is a result, not a loading failure',()=>{
 const empty={...data,ranked_symbols:[],continuing_ranked_symbols:[],new_nomination_symbols:[],selected_symbols:[],reviews:[]};
 const html=renderToStaticMarkup(React.createElement(compiledModule.exports.CandidateView,{data:empty}));
 assert.match(html,/没有匹配股票/);assert.doesNotMatch(html,/正在读取/);
});
test('all ranked and selected display rows preserve backend identity and exclude unavailable rows',()=>{
 assert.ok(fs.statSync(new URL('../public/cr056-ranking.json',import.meta.url)).size<750000);
 assert.equal(data.result_role,'legacy_comparison');
 assert.equal(typeof data.automatic_updates_connected,'boolean');
 assert.deepEqual(data.selected_symbols,data.ranked_symbols.slice(0,5));
 data.ranked_symbols.forEach((s,i)=>{
  const r=data.reviews.find(r=>r.symbol===s);
  assert.equal(r.rank,i+1);assert.ok(r.total!==null);assert.ok(r.coverage>=0.8);
 });
 const page=fs.readFileSync(new URL('../app/zh/watch/resonance/rare-opportunities/page.tsx',import.meta.url),'utf8');
 assert.doesNotMatch(page,/showLegacy|unified-v2-rankings|opportunity-ledger|TimeframeProfilePanel/);
 assert.match(page,/<CandidateRanking\/>/);
});

test('daily refresh failure retains the actual snapshot date and shows failure',()=>{
 const current={...data,automatic_updates_connected:true,refresh_status:{status:'failed',target_as_of:'2026-09-08'}};
 const html=renderToStaticMarkup(React.createElement(compiledModule.exports.CandidateView,{data:current,latestDate:new Date(Date.parse(data.as_of+'T00:00:00Z')+7*86400000).toISOString().slice(0,10)}));
 assert.match(html,/随现有日终流程自动复评/);assert.match(html,/自动复评未完成/);
 assert.ok(html.includes(data.as_of));assert.match(html,/更新落后/);
});


test('independent context keeps date mismatch, classification and holdings separate',()=>{
 const context={as_of:'2026-09-04',themes:[{theme_id:'semiconductors',reference_etf:'SOXX',members:['AAA'],membership_as_of:'2026-08-26'}],funds:{SOXX:{available:false,state:'Unavailable',latest_bar:'2026-08-28'}},ticker_themes:{AAA:['semiconductors']},classifications:{AAA:{sector:'Technology',industry:'Semiconductors'}},classification_as_of:'2026-08-28',coverage:{available_etfs:0,reference_etfs:21,themes:26,dated_membership_themes:19}};
 const market={as_of:'2026-09-04',funds:Array(17).fill({}),layers:{trend:{state:'supportive'},breadth:{state:'narrow_or_mixed'},risk_appetite:{state:'risk_seeking'}}};
 const render=symbol=>renderToStaticMarkup(React.createElement(contextModule.exports.ContextView,{context,market,symbol,asOf:'2026-09-08'}));
 const html=render('AAA');
 assert.match(html,/不作为同日背景/);assert.match(html,/ETF行情不可用/);assert.match(html,/2026-08-26/);assert.match(html,/2026-08-28/);
 assert.match(html,/FinanceDatabase/);assert.match(html,/不等于 ETF 实际持仓/);assert.match(html,/17 ETF/);
 assert.match(render('BBB'),/不据此排除候选/);
});

test('industry overview separates cards, pending evidence and dated holdings',()=>{
 const context=JSON.parse(fs.readFileSync(new URL('../public/industry-radar.json',import.meta.url),'utf8')).display_context;
 const market=JSON.parse(fs.readFileSync(new URL('../public/market-etf-watch.json',import.meta.url),'utf8'));
 const html=renderToStaticMarkup(React.createElement(contextModule.exports.ContextView,{context,market,candidates:data.ranked_symbols,candidateDate:data.as_of}));
 assert.equal((html.match(/class="industryContextCard"/g)||[]).length,context.themes.length);
 assert.match(html,/industryContextSummary/);assert.match(html,/industryContextGrid/);assert.match(html,/industryContextPending/);
 assert.match(html,/持仓代码/);assert.match(html,/含未核资产类型/);assert.doesNotMatch(html,/已解析股票/);
 const linked=context.themes.flatMap(t=>t.members).find(s=>data.ranked_symbols.includes(s));
 if(linked)assert.ok(html.includes(`/zh/watch/resonance/rare-opportunities?symbol=${encodeURIComponent(linked)}`));
 assert.match(html,/官方ETF来源/);assert.match(html,/持仓来源/);
 const css=fs.readFileSync(new URL('../app/product-v2.css',import.meta.url),'utf8');
 assert.match(css,/industryContextCompact \.industryContextGrid\{grid-template-columns:1fr/);
 assert.match(css,/\.industryContextHoldings span\{[^}]*user-select:all/);
});

test('candidate query selects the linked stock without changing backend ranking',()=>{
 const target=data.ranked_symbols.at(-1);
 const before=JSON.stringify(data);
 const html=renderToStaticMarkup(React.createElement(compiledModule.exports.CandidateView,{data,initialQuery:target}));
 assert.ok(html.includes(`${target} · 分项与原因`));
 assert.equal((html.match(/class="v2RankRow isSelected"/g)||[]).length,1);
 assert.equal(JSON.stringify(data),before);
});
