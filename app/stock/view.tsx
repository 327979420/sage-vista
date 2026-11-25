'use client';
import {useEffect, useState} from 'react';
import {useLocale} from '../i18n/locale';
import {sharedJson} from '../json-cache';
import {trackEvent} from '../analytics';
import SignalChart from '../app/signal-chart';
import {toRow, type SignalRow} from '../app/signal-rows';
import {fetchEvidence, validTicket} from '../evidence/data';
import {Mini, type SetupRow} from '../zh/watch/resonance/favorite-pattern/terminal';
import {W3_URLS, classify, family, findings, lights, priceFacts, stockHref, type Entry, type Lookup, type Part, type StockIndex} from './lookup';
import {StockSearch, useIndex} from './search';

const md = (d: string | null | undefined) => (d ?? '').slice(5);
const STOCK_HOME = '/stock';
const money = (v: number) => `$${v.toFixed(2)}`;

const text = (parts: Part[]) => parts.map((p, i) => typeof p === 'string' ? <span key={i}>{p}</span> : <b key={i}>{p.b}</b>);

function Findings({index, en}: {index: StockIndex; en: boolean}) {
 const {summary, rows} = findings(index, en);
 return <section className="slFind">
  <p className="slSum">{text(summary)}</p>
  <div className="slRows">{rows.map(r => <div key={r.key} className="slRow" data-tone={r.tone}>
   <div className="slLab"><b>{r.title}</b><small>{r.note}</small></div>
   <div className="slChips">{r.symbols.map(s => <a key={s} href={stockHref(s)}>{s}</a>)}
    {r.more && (r.href ? <a className="slMore" href={r.href}>{r.more} →</a> : <em>{r.more}</em>)}
    {!r.more && r.href && <a className="slMore" href={r.href}>{en ? 'See all →' : '看全部 →'}</a>}</div>
  </div>)}</div>
  <p className="slHint">{en ? 'Not listed? Search any US ticker above.' : '没提到的？在上面搜任何美股代码。'}</p>
 </section>;
}

function W3Detail({entry, en}: {entry: Entry; en: boolean}) {
 const [row, setRow] = useState<SignalRow | null | undefined>(undefined);
 useEffect(() => {
  const control = new AbortController(), w3 = entry.w3!;
  void (async () => {
   const signals = await sharedJson<{signals: {id: string}[]}>(W3_URLS.signals);
   const signal = signals?.signals.find(s => s.id === w3.id);
   const ticket = signal ? await fetchEvidence(`/app/tickets/${encodeURIComponent(w3.id)}.json`, validTicket, control.signal) : null;
   setRow(signal ? toRow(signal as Parameters<typeof toRow>[0], ticket && !ticket.example ? ticket : null) : null);
  })();
  return () => control.abort();
 }, [entry]);
 if (row === undefined) return <div className="slChart"><p className="slQuiet">{en ? 'Loading the weekly chart…' : '正在读取周线…'}</p></div>;
 if (!row) return null;
 const verdict = row.status === 'skipped' ? (row.ruleOk ? (en ? 'Stopped by market' : '大盘拦下') : (en ? 'Failed the rule' : '规则不过')) : (en ? 'Ordered' : '已下单');
 return <>
  <div className="slChart"><header>{en ? 'Weekly · falling highs, bottoms and the plan' : '周线 · 三推下降线、底部和计划价位'}</header><SignalChart r={row} en={en}/></div>
  <div className="slFact"><h3>{en ? `3W signal · week of ${row.week}` : `3W 信号 · ${row.week} 那周`}</h3>
   <p><b>{verdict}</b>{en ? `. Shape checks ${row.shapePassed}/${row.shapeTotal}` : `。形态检查 ${row.shapePassed}/${row.shapeTotal} 过了`}
    {row.rr !== null && (en ? `; reward/risk ${row.rr.toFixed(2)} (needs 1.5)` : `；盈亏比 ${row.rr.toFixed(2)}（要 ≥1.5）`)}.</p>
   <div className="slPlan"><span><i>{en ? 'limit' : '限价'}</i> {money(row.limit)}</span><span><i>{en ? 'stop' : '止损'}</i> {money(row.stop)}</span><span><i>{en ? 'target' : '目标'}</i> {money(row.target)}</span></div>
   <a href="/signals">{en ? 'All of this signal’s checks →' : '看这个信号的全部检查 →'}</a></div>
 </>;
}

function ShapeDetail({symbol, en, chart}: {symbol: string; en: boolean; chart: boolean}) {
 const [row, setRow] = useState<SetupRow | null | undefined>(undefined);
 useEffect(() => {
  let on = true;
  sharedJson<{rows: SetupRow[]}>('/daily-shape-picker.json').then(p => { if (on) setRow(p?.rows?.find(r => r.symbol === symbol) ?? null); });
  return () => { on = false; };
 }, [symbol]);
 if (!row) return null;
 return <>
  {chart && <div className="slChart"><header>{en ? 'Daily · support zone, falling push line, invalidation' : '日线 · 底部区间、下降趋势线和作废线'}</header><div className="slMini"><Mini row={row}/></div></div>}
  <div className="slFact"><h3>{en ? 'Daily setup' : '日线形态'}</h3>
   <p>{en ? `Support zone ${money(row.bottom.zone_lower)}–${money(row.bottom.zone_upper)}; the setup is void below ${money(row.invalidation_price)}.` : `底部区间 ${money(row.bottom.zone_lower)}–${money(row.bottom.zone_upper)}，跌破 ${money(row.invalidation_price)} 形态作废。`}</p>
   <a href="/patterns">{en ? 'All of today’s setups →' : '看今天全部形态 →'}</a></div>
 </>;
}

function Card({symbol, entry, index, en}: {symbol: string; entry: Entry; index: StockIndex; en: boolean}) {
 const url = `https://sage.freddyliang.com${stockHref(symbol)}`;
 const [copied, setCopied] = useState('');
 const facts = priceFacts(entry, en);
 const quiet = !entry.w3 && !entry.sh && entry.mf === undefined;
 return <article className="slCard">
  <header className="slHead"><h1>{symbol}</h1>
   {entry.c !== null && <span className="slPx">{money(entry.c)} · {en ? `${md(index.as_of)} close` : `${md(index.as_of)} 收盘`}</span>}
   <span className="slChip" data-on="">{en ? 'SV tracks it' : 'SV 在跟'}</span>
   <div className="slShare"><code>{url.replace('https://', '')}</code>
    <button type="button" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(en ? 'Copied' : '已复制'), () => setCopied(en ? 'Copy it by hand' : '请手动复制'))}>{copied || (en ? 'Copy link' : '复制链接')}</button></div>
  </header>
  <div className="slLights">{lights(entry, index, en).map((l, i) => <div key={i} className="slLight" data-tone={l.tone}>
   <small>{[en ? '3W weekly rule' : '3W 周线规则', en ? 'Daily setup' : '日线形态', en ? 'Multi-factor' : '多因子'][i]}</small><b>{l.title}</b><span>{l.note}</span></div>)}</div>
  <div className="slBody">
   {entry.w3 && <W3Detail entry={entry} en={en}/>}
   {entry.sh && <ShapeDetail symbol={symbol} en={en} chart={!entry.w3}/>}
   {(entry.mf ?? -1) >= 0 && <div className="slFact"><h3>{en ? 'Multi-factor · today' : '多因子 · 今天'}</h3>
    <p>{entry.mf ? (en ? `Factors agreeing: ${(entry.f ?? []).map(f => family(f, true)).join(', ')}.` : `看好的因子：${(entry.f ?? []).map(f => family(f, false)).join('、')}。`) : (en ? 'Its daily MACD crossed today, but it is not in the top candidates.' : '日线 MACD 今天金叉，但没进前面的候选。')}
     {en ? ' The rank orders review, it is not a win rate.' : '排名是复核顺序，不是胜率。'}</p>
    <a href="/multi-factor">{en ? 'Today’s candidate list →' : '看今天的候选榜 →'}</a></div>}
   {facts.length > 0 && <div className="slFact"><h3>{en ? 'Price' : '走势'}</h3><p>{facts.join(en ? ' · ' : ' · ')}</p>
    {quiet && <p className="slQuiet">{en ? 'SV checks this stock after every close. Nothing is happening today; this page lights up when it does.' : 'SV 每天收盘后都会算这只。今天三项都没动静，出信号时这一页会亮。'}</p>}</div>}
  </div>
 </article>;
}

function Missing({lookup, index, en}: {lookup: Exclude<Lookup, {kind: 'tracked'} | {kind: 'empty'}>; index: StockIndex; en: boolean}) {
 const [asked, setAsked] = useState(false);
 const busy = findings(index, en).rows.filter(r => r.key !== 'big').flatMap(r => r.symbols).slice(0, 6);
 const rule = en ? `SV tracks US-listed stocks that close at $${index.rule.min_close} or more, trade at least $${index.rule.min_dollar_volume / 1e6}M a day and have ${index.rule.min_sessions}+ sessions of history.`
  : `SV 跟的是美国上市的股票：收盘价不低于 ${index.rule.min_close} 美元，日成交额不低于 ${index.rule.min_dollar_volume / 1e4} 万美元，至少 ${index.rule.min_sessions} 个交易日的历史。`;
 return <article className="slCard">
  {lookup.kind === 'chinese' ? <header className="slHead"><h1>{en ? 'Search by ticker' : '先用股票代码搜'}</h1></header>
   : <header className="slHead"><h1>{lookup.symbol}</h1><span className="slChip">{en ? 'Not tracked by SV' : 'SV 没在跟'}</span></header>}
  <p className="slLead">{lookup.kind === 'chinese' ? (en ? 'For example NVDA or CSCO. Company names are not searchable yet.' : '比如 NVDA、CSCO。公司名（尤其中文名）暂时搜不了。')
   : lookup.kind === 'not_us' ? (en ? 'This looks like a non-US ticker. SV only covers US stocks for now.' : '这像是港股、A 股或其他市场的代码。SV 现在只看美股。')
   : (en ? `${lookup.symbol} is not on today’s list of ${index.count.toLocaleString('en-US')} stocks.` : `${lookup.symbol} 不在今天的 ${index.count.toLocaleString('zh-CN')} 只名单里。`)}</p>
  {lookup.kind !== 'chinese' && <p className="slQuiet">{rule}</p>}
  {lookup.kind === 'not_tracked' && <div><button className="slWant" type="button" disabled={asked} onClick={() => { setAsked(true); trackEvent('stock_track_requested', {symbol: lookup.symbol}); }}>
   {asked ? (en ? 'Noted. Thanks.' : '记下了，谢谢。') : (en ? 'Ask SV to track it' : '想让 SV 跟这只')}</button></div>}
  {busy.length > 0 && <div className="slTry"><small>{en ? 'Something is happening with these today' : '今天有动静的'}</small><div className="slChips">{busy.map(s => <a key={s} href={stockHref(s)}>{s}</a>)}</div></div>}
 </article>;
}

export default function StockLookup({symbol}: {symbol?: string}) {
 const {locale} = useLocale(), en = locale === 'en';
 const {index, ready} = useIndex();
 const lookup = symbol ? classify(symbol, index) : null;
 return <main className="rtPage svTerminalPage"><div className="slRoot">
  <section className="slTop">
   {lookup ? <a className="slBack" href={STOCK_HOME}>{en ? '← What SV saw today' : '← 今天 SV 看到了什么'}</a>
    : <h1>{en ? 'What SV saw today' : '今天 SV 看到了什么'}{index && <span>{en ? `${md(index.as_of)} close · ${index.count.toLocaleString('en-US')} stocks` : `${md(index.as_of)} 收盘 · ${index.count.toLocaleString('zh-CN')} 只`}</span>}</h1>}
   <StockSearch initial={lookup && lookup.kind !== 'empty' && lookup.kind !== 'chinese' ? lookup.symbol : ''}/>
  </section>
  {!ready ? <p className="slQuiet">{en ? 'Reading today’s list…' : '正在读取今天的名单…'}</p>
   : !index ? <p className="slLead">{en ? 'The lookup list is being prepared. It appears after the next daily update.' : '查股票的名单还在准备，下一次日更后就有。'}</p>
   : !lookup || lookup.kind === 'empty' ? <Findings index={index} en={en}/>
   : lookup.kind === 'tracked' ? <Card symbol={lookup.symbol} entry={lookup.entry} index={index} en={en}/>
   : <Missing lookup={lookup} index={index} en={en}/>}
  {index && <p className="slFoot">{en ? `What SV’s rules say, not investment advice. The 3W rule (v1.9) is locked and not proven yet: ${index.closed} of 100 trades closed.`
   : `这是 SV 规则的判断，不是投资建议。3W 规则 v1.9 已锁定，还没被证明：已平仓 ${index.closed} / 100 笔。`}</p>}
 </div></main>;
}
