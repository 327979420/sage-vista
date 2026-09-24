import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {loadTs} from './helpers/load-ts.mjs';
const {LocaleProvider,Localized,LanguageSwitch,localizeNodes,saveLocalePreference,normalizeLocale}=loadTs('app/i18n/locale.tsx');
const {translate}=loadTs('app/i18n/messages.ts');
const data=name=>JSON.parse(fs.readFileSync(`public/${name}.json`,'utf8'));
const market=loadTs('app/zh/watch/market/dashboard.tsx');
const industry=loadTs('app/zh/watch/industry-radar/dashboard.tsx');
const candidate=loadTs('app/zh/watch/resonance/rare-opportunities/cr056-ranking.tsx');
const picker=loadTs('app/zh/watch/resonance/favorite-pattern/page.tsx');
const comparison=loadTs('app/zh/backtest/comparison.tsx');
const research=loadTs('app/zh/backtest/research-runs.tsx');
const sample=data('market-internals'),candidates=data('cr056-ranking'),patterns=data('daily-shape-picker');
const render=(component,props={},locale='en')=>renderToStaticMarkup(React.createElement(LocaleProvider,{initialLocale:locale},React.createElement(component,props)));
const visible=html=>html.replace(/<[^>]*>/g,'');
const assertEnglish=html=>{assert.doesNotMatch(visible(html),/[\u3400-\u9fff]/);for(const match of html.matchAll(/(?:aria-label|title|placeholder)="([^"]*)"/g))assert.doesNotMatch(match[1],/[\u3400-\u9fff]/);};

test('real saved snapshots render English without changing inputs, dates, prices or ranks',()=>{
 const views=[
  [market.MarketView,{cockpit:data('market-cockpit'),sample,targetDate:sample.as_of}],
  [industry.IndustryView,{context:data('industry-radar').display_context,targetDate:sample.as_of,candidates:candidates.ranked_symbols,candidateDate:candidates.as_of}],
  [candidate.CandidateView,{data:candidates,latestDate:candidates.as_of}],
  [picker.DailyPatternView,{data:patterns,onRetry:()=>{}}],
  [comparison.ComparisonView,{reports:data('vectorbt-comparison').reports}],
  [research.default,{}]
 ];
 for(const[component,props]of views){
  const before=JSON.stringify(props),en=render(component,props),zh=render(component,props,'zh');
  assertEnglish(en);assert.match(visible(zh),/[\u3400-\u9fff]/);assert.equal(JSON.stringify(props),before);
  const observations=html=>[...html.replace(/(\d{4})年(\d{2})月(\d{2})日/g,'$1-$2-$3').matchAll(/20\d\d-\d\d-\d\d|[+-]\d+(?:\.\d+)?%/g)].map(m=>m[0]);
  assert.deepEqual(observations(en),observations(zh));
  const geometry=html=>[...html.matchAll(/(?:d|points|cx|cy|x|y|width|height)="[^"<>]*"/g)].map(m=>m[0]);
  assert.deepEqual(geometry(en),geometry(zh));
 }
 const en=render(candidate.CandidateView,{data:candidates,latestDate:candidates.as_of});
 const zh=render(candidate.CandidateView,{data:candidates,latestDate:candidates.as_of},'zh');
 const ranks=html=>[...html.matchAll(/#(\d+) · ([A-Z.]+)/g)].map(m=>m[0]);
 assert.deepEqual(ranks(en),ranks(zh));
 for(const symbol of candidates.continuing_ranked_symbols.slice(0,50)){const row=candidates.reviews.find(r=>r.symbol===symbol);assert.ok(en.includes(row.total.toFixed(2)));assert.ok(en.includes(`$${row.price}`));}
 assert.ok(render(market.MarketView,views[0][1]).includes(sample.as_of));
 assert.ok(render(picker.DailyPatternView,views[3][1]).includes(patterns.as_of));
});

test('English errors, stale dates, empty results and missing figures remain explicit',()=>{
 const stale=render(candidate.CandidateView,{data:{...candidates,automatic_updates_connected:true,refresh_status:{status:'failed'}},latestDate:new Date(Date.parse(candidates.as_of+'T00:00:00Z')+86400000).toISOString().slice(0,10)});
 assertEnglish(stale);assert.match(stale,/Update delayed|Automatic review incomplete/);assert.ok(stale.includes(candidates.as_of));
 const empty=render(candidate.CandidateView,{data:{...candidates,reviews:[],ranked_symbols:[],continuing_ranked_symbols:[],new_nomination_symbols:[],selected_symbols:[]}});
 assertEnglish(empty);assert.match(empty,/No matching stocks/);
 const missing=render(market.MarketView,{cockpit:null,sample:null,targetDate:sample.as_of});
 assertEnglish(missing);assert.match(missing,/Data not yet available/);assert.doesNotMatch(missing,/0\.0%/);
 const error=render(picker.DailyPatternView,{data:null,error:'形态数据暂时无法读取，请重试。',onRetry:()=>{}});
 assertEnglish(error);assert.match(error,/Unable to read pattern data/);assert.match(error,/Reload/);
});

test('display localization preserves React keys, callbacks, input values and business props',()=>{
 let chosen='';const onClick=()=>{chosen='monthly_completed'};
 const Custom=()=>null;
 const children=[React.createElement('button',{key:'monthly_completed',onClick,'data-frame':'monthly_completed',title:'查看详情'},'月线'),React.createElement('input',{key:'query',value:'月线',placeholder:'搜索股票代码',onChange:()=>{}}),React.createElement(Custom,{key:'custom',active:'大盘',title:'大盘'})];
 const translated=localizeNodes(children,'en');
 assert.deepEqual(translated.map(n=>n.key),children.map(n=>n.key));
 assert.equal(translated[0].props.children,'Monthly');assert.equal(translated[0].props.title,'View details');assert.equal(translated[0].props['data-frame'],'monthly_completed');
 translated[0].props.onClick();assert.equal(chosen,'monthly_completed');assert.equal(translated[0].props.onClick,onClick);
 assert.equal(translated[1].props.value,'月线');assert.equal(translated[1].props.placeholder,'Search ticker');
 assert.equal(translated[2],children[2]);assert.equal(translated[2].props.active,'大盘');
 const raw=React.createElement('code',null,'月线');assert.equal(localizeNodes(raw,'en'),raw);
 assert.deepEqual(localizeNodes(children,'zh').map(n=>n.key),translated.map(n=>n.key));
});

test('switch has accessible pressed state; preference works across paths and storage denial is harmless',()=>{
 const en=render(LanguageSwitch),zh=render(LanguageSwitch,{},'zh');
 assert.match(en,/lang="en" aria-pressed="true"/);assert.match(zh,/lang="zh-CN" aria-pressed="true"/);
 assert.equal(normalizeLocale('en'),'en');assert.equal(normalizeLocale('unexpected'),'en');assert.equal(normalizeLocale(undefined),'en');assert.equal(normalizeLocale('zh'),'zh');
 const fallback=renderToStaticMarkup(React.createElement(LocaleProvider,null,React.createElement(LanguageSwitch)));
 assert.match(fallback,/lang="en" aria-pressed="true"/);
 const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document'),oldWindow=Object.getOwnPropertyDescriptor(globalThis,'window');
 try{
  Object.defineProperty(globalThis,'document',{value:{cookie:''},configurable:true});Object.defineProperty(globalThis,'window',{value:{location:{protocol:'https:'}},configurable:true});
  // Session cookie only: no Max-Age/Expires, so every new visit opens in English.
  saveLocalePreference('en');assert.equal(document.cookie,'sv-language-session=en; Path=/; SameSite=Lax; Secure');
  saveLocalePreference('zh');assert.match(document.cookie,/^sv-language-session=zh;/);assert.doesNotMatch(document.cookie,/Max-Age|Expires/i);
  Object.defineProperty(document,'cookie',{set(){throw Error('Storage disabled')},configurable:true});assert.doesNotThrow(()=>saveLocalePreference('en'));
 }finally{if(oldDocument)Object.defineProperty(globalThis,'document',oldDocument);else delete globalThis.document;if(oldWindow)Object.defineProperty(globalThis,'window',oldWindow);else delete globalThis.window;}
});

test('numeric templates and dynamic backend labels preserve financial meaning',()=>{
 assert.equal(translate('新低数量约为新高的 2.0 倍。','en'),'New lows outnumber new highs by about 2.0 to 1.');
 assert.equal(translate('周度净仓占比变化 +4.5个百分点','en'),'Weekly net-positioning share change: +4.5 pp');
 assert.equal(translate('2个低点已确认；未识别到合格三推，不贴三推标签。','en'),'2 lows confirmed; no qualifying three-push structure identified.');
 assert.equal(translate('未知新说明','en'),'未知新说明');
 assert.equal(picker.turnover(1e8,'en'),'$100M');assert.equal(picker.turnover(1e9,'en'),'$1B');assert.equal(picker.turnover(2.5e7,'en'),'$25M');assert.equal(picker.turnover(1e8,'zh'),'1.0 亿美元');
 for(const row of patterns.rows){for(const key of ['state_zh','shape_zh','explanation_zh'])assert.doesNotMatch(translate(row[key],'en'),/[\u3400-\u9fff]/);}
 for(const f of Object.values(candidates.factor_catalog))assert.doesNotMatch(translate(f.name.replace(/(\d+)日/g,'$1根'),'en'),/[\u3400-\u9fff]/);
 assert.match(render(Localized,{children:'Customer包含个人和机构账户，不代表散户；成交量不等于仓位。'}),/not just retail; volume is not positioning/);
});

test('active UI copy has reviewed English entries, including rare states and detail text',async()=>{
 const ts=(await import('typescript')).default;
 const {catalog}=loadTs('app/i18n/catalog.ts');
 const files=['watch/resonance/tracker-ui.tsx','watch/market/dashboard.tsx','watch/market/interpretation.ts','watch/industry-radar/dashboard.tsx','watch/industry-radar/context.tsx','watch/resonance/rare-opportunities/cr056-ranking.tsx','watch/resonance/rare-opportunities/page.tsx','watch/resonance/favorite-pattern/page.tsx','watch/resonance/about/page.tsx','backtest/page.tsx','backtest/research-runs.tsx','backtest/comparison.tsx'];
 for(const file of files){
  const source=ts.createSourceFile(file,fs.readFileSync(`app/zh/${file}`,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const visit=node=>{let text;if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)||ts.isJsxText(node))text=node.text;
   if(ts.isTemplateExpression(node))text=node.head.text+node.templateSpans.map((part,i)=>`{${i}}`+part.literal.text).join('');
   if(text&&/[\u3400-\u9fff]/.test(text)){assert.ok(Object.hasOwn(catalog,text.trim()),`${file}: missing translation for ${text.trim()}`);assert.doesNotMatch(catalog[text.trim()],/[\u3400-\u9fff]/);}
   ts.forEachChild(node,visit);
  };visit(source);
 }
});
