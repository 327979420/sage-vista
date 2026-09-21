import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import {loadTs as load} from './helpers/load-ts.mjs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const root=path.resolve('app/zh/watch');
const dashboard=load(path.join(root,'market/dashboard.tsx'));
const interpretation=load(path.join(root,'market/interpretation.ts'));
const industry=load(path.join(root,'industry-radar/dashboard.tsx'));
const data=name=>JSON.parse(fs.readFileSync(`public/${name}.json`,'utf8'));
const cockpit=data('market-cockpit'),sample=data('market-internals'),context=data('industry-radar').display_context;
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
test('cockpit renders actual observations in eight distinct cards without the rejected indicators',()=>{
 const html=render(dashboard.MarketView,{cockpit,sample,targetDate:sample.as_of});
 assert.equal((html.match(/class="cockpitCard"/g)||[]).length,8);
 for(const name of ['资金流向','机构仓位','市场融资','期权成交结构','市场参与','市场突破','市场领导力','行业扩散'])assert.ok(html.includes(name));
 assert.match(html,/410/);assert.match(html,/759/);assert.match(html,/1,172/);assert.match(html,/不代表整个美股市场/);
 assert.match(html,/44.8/);assert.match(html,/1.454/);assert.match(html,/2026-08-31/);assert.match(html,/2026-09-15/);
 assert.doesNotMatch(html,/VIX|风险温度|source_sha256|Cboe|Yahoo|ICI|均线|总体风险/);
 assert.match(html,/这项数据暂未取得/);assert.match(html,/Customer包含个人和机构/);
});
test('a mismatched bundle date never shows previous observations as today',()=>{
 const html=render(dashboard.MarketView,{cockpit,sample,targetDate:'2099-01-01'});
 assert.match(html,/这项数据暂未取得/);assert.doesNotMatch(html,/>410<|>759<|44.8|1.454/);
});
test('future observations and degraded breadth are isolated instead of fabricated',()=>{
 const broken=structuredClone(cockpit);broken.panels.margin.observation_date='2099-01-01';
 const badSample=structuredClone(sample);badSample.history.at(-1).quality.status='degraded';
 const html=render(dashboard.MarketView,{cockpit:broken,sample:badSample,targetDate:sample.as_of});
 assert.doesNotMatch(html,/>410<|>759<|1.454/);assert.match(html,/44.8/);
});
test('missing options does not turn into zero while other sources remain readable',()=>{
 const broken=structuredClone(cockpit);broken.panels.options={id:'options',status:'unavailable',frequency:'daily',observation_date:null};
 const html=render(dashboard.MarketView,{cockpit:broken,sample,targetDate:sample.as_of});
 const optionsCard=html.split('aria-labelledby="card-options"')[1].split('</section>')[0];
 assert.doesNotMatch(optionsCard,/44\.8|0\.0%/);assert.match(html,/1.454/);assert.match(optionsCard,/这项数据暂未取得/);
});
test('industry keeps all themes but moves the market and source clutter off its page',()=>{
 const html=render(industry.IndustryView,{context,targetDate:context.as_of});
 assert.equal((html.match(/class="mvpIndustryCard"/g)||[]).length,context.themes.length);
 assert.match(html,/待补数据的主题/);assert.match(html,/搜索行业或ETF/);assert.match(html,/相关候选/);assert.match(html,/回到60日高点需涨/);assert.match(html,/20\.1%/);assert.doesNotMatch(html,/-20\.1%/);
 assert.doesNotMatch(html,/大盘环境|官方ETF来源|持仓来源|source_sha256|旧成员广度|SPY/);
});
test('industry stale fund dates and stale candidate lists cannot appear current',()=>{
 const broken=structuredClone(context);for(const f of Object.values(broken.funds))f.latest_bar='2000-01-01';
 const html=render(industry.IndustryView,{context:broken,targetDate:context.as_of,candidates:['ZZZ'],candidateDate:'2000-01-01'});
 assert.doesNotMatch(html,/data-state="Uptrend"|data-state="Rising Pullback At Support"|symbol=ZZZ/);
 assert.match(html,/等待更新/);
});

test('daily level and direction are independent; weak can improve',()=>{
 const latest=structuredClone(sample.history.at(-1));
 const prior=structuredClone(latest);prior.counts.advances=100;prior.counts.declines=1069;
 const result=interpretation.participation(latest,prior);
 assert.equal(result.level,'偏弱');assert.equal(result.direction.label,'改善');
 assert.equal(result.evidence[0].value,'35.0%');
});
test('a nominally complete report with missing members cannot produce a normal state',()=>{
 const latest=structuredClone(sample.history.at(-1));latest.quality.valid_ticker_count-=1;latest.counts.declines-=1;
 const result=interpretation.participation(latest,latest);
 assert.equal(result.available,false);assert.match(result.explanation,/覆盖不足/);assert.equal(result.direction.label,'待比较');
});
test('breakout zero counts and changing denominators never fabricate ratios or direction',()=>{
 const latest=structuredClone(sample.history.at(-1));const prior=structuredClone(latest);
 latest.counts.new_highs=0;latest.counts.new_lows=0;
 let result=interpretation.breakouts(latest,prior);assert.equal(result.level,'均衡');assert.doesNotMatch(result.explanation,/NaN|Infinity/);
 latest.counts.new_lows=38;result=interpretation.breakouts(latest,prior);assert.match(result.explanation,/没有新高/);
 prior.indicators.new_high_low.valid_count-=1;result=interpretation.breakouts(latest,prior);assert.equal(result.direction.label,'待比较');assert.match(result.direction.detail,/样本数不同/);
});
test('leadership describes relative weakness during a falling market rather than claiming an advance',()=>{
 const funds=structuredClone(cockpit.panels.quotes.funds);
 funds.find(f=>f.ticker==='SPY').returns['20']=-5;
 funds.find(f=>f.ticker==='RSP').returns['20']=-10;
 funds.find(f=>f.ticker==='IWM').returns['20']=-15;
 const result=interpretation.leadership(funds);
 assert.equal(result.level,'等权、小盘更弱');assert.equal(result.evidence[0].value,'-5.3%');
 assert.ok(Math.abs(interpretation.relativeReturn(funds.find(f=>f.ticker==='RSP'),funds.find(f=>f.ticker==='SPY'),20)-(-5.263157894736836))<1e-8);
});
test('weekly net exposure can improve without claiming gross short contracts fell',()=>{
 const c=structuredClone(cockpit.panels.positions.contracts[0]);
 let result=interpretation.positionReading(c);assert.equal(result.direction.label,'改善');assert.match(result.explanation,/净空敞口收窄/);assert.doesNotMatch(result.explanation,/空头合约减少/);
 c.history.at(-2).date='2000-01-01';result=interpretation.positionReading(c);assert.equal(result.direction.label,'待比较');
});
test('margin growth is a neutral fact; options are not a retail position signal',()=>{
 const reading=interpretation.marginReading(cockpit.panels.margin);
 assert.equal(reading.direction.label,'上升');assert.equal(reading.tone,'neutral');assert.match(reading.basis,/不代表纯散户/);
 const html=render(dashboard.MarketView,{cockpit,sample,targetDate:sample.as_of});
 assert.match(html,/每日辅助 · 期权成交结构/);assert.match(html,/不代表散户/);
});
test('actual page order follows daily, weekly, monthly with missing flow last',()=>{
 const html=render(dashboard.MarketView,{cockpit,sample,targetDate:sample.as_of});
 const order=[...html.matchAll(/class="cockpitCard" aria-labelledby="card-([a-z]+)"/g)].map(m=>m[1]);
 assert.deepEqual(order,['breadth','relative','highs','sectors','options','positions','margin','flows']);
 assert.match(html,/市场概况/);assert.match(html,/每周 · <!-- -->2026-09-15|每周 · 2026-09-15|每周.*2026-09-15/);
 const daily=html.split('aria-labelledby="daily-market"')[1].split('</section></div></section>')[0];
 assert.doesNotMatch(daily,/class="cockpitChart"|历史位置|98\.7|93\.1/);
});
test('stale weekly and monthly facts stay out of the current Market Read',()=>{
 const broken=structuredClone(cockpit);broken.panels.positions.status='stale';broken.panels.margin.status='stale';
 const html=render(dashboard.MarketView,{cockpit:broken,sample,targetDate:sample.as_of});
 const read=html.split('aria-label="市场概况"')[1].split('</section>')[0];
 assert.doesNotMatch(read,/净空|融资使用/);assert.match(read,/市场参与/);
});
