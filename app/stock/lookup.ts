// Stock lookup: what SV's three views say about one stock, from public/stock-index.json
// (written by services/scanner/stock_lookup.py after each daily update). Pure functions only,
// so the page, the top-bar search and the tests share one reading of the index.

export type Shape = 'waiting' | 'broken_out' | 'retest';
export type Entry = {c: number | null; x?: true; m6?: number; hi?: number; ma?: boolean;
 mf?: number; h?: number | null; f?: string[]; sh?: Shape; a?: number | null; w3?: {id: string; week: string; status: string}};
export type StockIndex = {schema_version: number; as_of: string; count: number; mf_triggered: number; mf_ranked: number;
 shape_watch: number | null; shape_counts: Record<string, number>;
 w3: {as_of: string | null; week: string | null; new: number | null; light: string | null; latest_week: string | null; latest: string[]; since_lock: number};
 rule: {min_close: number; min_dollar_volume: number; min_sessions: number};
 closed: number; big: string[]; new: {mf: string[]; sh: string[]; w3: string[]}; new_since: string | null; stocks: Record<string, Entry>};

export const INDEX_URL = '/stock-index.json';
export const stockHref = (symbol: string) => `/stock/${encodeURIComponent(symbol)}`;

export function validIndex(v: unknown): v is StockIndex {
 const i = v as StockIndex;
 return !!i && typeof i === 'object' && i.schema_version === 1 && typeof i.as_of === 'string' && Number.isInteger(i.count)
  && !!i.stocks && typeof i.stocks === 'object' && Array.isArray(i.big) && !!i.new && !!i.w3;
}

// Exchange-listed US tickers: letters, sometimes a class suffix (BRK-B, BRK.B). Anything with
// digits or an exchange suffix (0700.HK, 600519.SS, 7203.T) is a market SV does not cover.
const US = /^[A-Z]{1,5}([.-][A-Z]{1,2})?$/;
export type Lookup = {kind: 'empty'} | {kind: 'chinese'} | {kind: 'not_us' | 'not_tracked'; symbol: string} | {kind: 'tracked'; symbol: string; entry: Entry};

export function classify(input: string, index: StockIndex | null): Lookup {
 const raw = input.trim();
 if (!raw) return {kind: 'empty'};
 if (/[㐀-鿿]/.test(raw)) return {kind: 'chinese'};
 const symbol = raw.toUpperCase().slice(0, 16);
 if (!US.test(symbol)) return {kind: 'not_us', symbol};
 const key = index && [symbol, symbol.replace('.', '-')].find(k => index.stocks[k]);
 return key ? {kind: 'tracked', symbol: key, entry: index!.stocks[key]} : {kind: 'not_tracked', symbol};
}

const busy = (e: Entry) => e.mf !== undefined || !!e.sh || !!e.w3;
export function suggest(prefix: string, index: StockIndex, limit = 7): string[] {
 const p = prefix.trim().toUpperCase().replace('.', '-');
 if (!p || !/^[A-Z-]+$/.test(p)) return [];
 return Object.keys(index.stocks).filter(s => s.startsWith(p))
  .sort((a, b) => (a === p ? -1 : b === p ? 1 : 0) || Number(busy(index.stocks[b])) - Number(busy(index.stocks[a])) || a.length - b.length || a.localeCompare(b))
  .slice(0, limit);
}

export const tags = (e: Entry, en: boolean) => [
 e.w3 && (en ? '3W signal' : '3W 信号'),
 e.sh && (en ? 'setup' : '形态'),
 e.mf !== undefined && (e.mf > 0 ? (en ? `multi-factor #${e.mf}` : `多因子第 ${e.mf}`) : (en ? 'multi-factor trigger' : '多因子触发')),
].filter(Boolean) as string[];

export type Tone = 'go' | 'wait' | 'stop' | 'off';
export type Light = {tone: Tone; title: string; note: string};
const SHAPE: Record<Shape, [Tone, string, string]> = {waiting: ['wait', '等待突破', 'Waiting to break out'], broken_out: ['go', '已突破', 'Broken out'], retest: ['wait', '回到趋势线', 'Back at the trend line']};
const md = (d: string | null) => (d ?? '').slice(5);
const n = (v: number, en: boolean) => v.toLocaleString(en ? 'en-US' : 'zh-CN');

// The three lights on a stock card: 3W weekly rule, daily setup, multi-factor.
export function lights(e: Entry, index: StockIndex, en: boolean): [Light, Light, Light] {
 const w3: Light = e.w3
  ? (e.w3.status === 'skipped'
   ? {tone: 'wait', title: en ? 'Signal · not ordered' : '有信号 · 没下单', note: en ? `Signal in the week of ${md(e.w3.week)}` : `${md(e.w3.week)} 那周出信号`}
   : {tone: 'go', title: en ? 'Signal · ordered' : '有信号 · 已下单', note: en ? `Signal in the week of ${md(e.w3.week)}` : `${md(e.w3.week)} 那周出信号`})
  : {tone: 'off', title: en ? 'No signal' : '没有信号', note: en ? `Not among the ${index.w3.since_lock} signals since the rule was locked` : `锁定以来 ${index.w3.since_lock} 个信号里没有它`};
 const watch = index.shape_watch ?? 100;
 const sh: Light = e.sh
  ? {tone: SHAPE[e.sh][0], title: en ? SHAPE[e.sh][2] : SHAPE[e.sh][1], note: en ? 'Three-push pullback onto multi-bottom support' : '三推回调＋多底支撑'}
  : {tone: 'off', title: en ? 'No setup' : '没有成形的形态', note: en ? `Looked for in the ${watch} most-traded stocks` : `只在成交最活跃的 ${watch} 只里找`};
 const mf: Light = e.mf
  ? {tone: 'go', title: en ? `Candidate #${e.mf} of ${index.mf_ranked}` : `候选第 ${e.mf} / ${index.mf_ranked}`,
   note: en ? `${e.h ?? '—'} factors agree across ${e.f?.length ?? 0} families` : `${e.h ?? '—'} 个因子看好 · ${e.f?.length ?? 0} 类`}
  : e.mf === 0
   ? {tone: 'wait', title: en ? 'Triggered today' : '今天触发', note: en ? `Not in the top ${index.mf_ranked}` : `没进前 ${index.mf_ranked} 候选`}
   : {tone: 'off', title: en ? 'Not triggered' : '今天没触发', note: en ? `${index.mf_triggered} of ${n(index.count, en)} triggered today` : `${n(index.count, en)} 只里 ${index.mf_triggered} 只触发`};
 return [w3, sh, mf];
}

export const FAMILY: Record<string, [string, string]> = {macd: ['MACD', 'MACD'], price_structure: ['价格结构', 'price structure'], qualification: ['长期资格', 'long-term trend'],
 support: ['支撑', 'support'], volume: ['成交量', 'volume'], rsi: ['RSI', 'RSI']};
export const family = (f: string, en: boolean) => (FAMILY[f] ? FAMILY[f][en ? 1 : 0] : f);

// Plain price facts for a stock with nothing happening: half-year change, distance from the year's high, 200-day line.
export function priceFacts(e: Entry, en: boolean): string[] {
 if (e.m6 === undefined || e.hi === undefined || e.ma === undefined) return [];
 const pct = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
 return en
  ? [`${pct(e.m6)} over six months`, e.hi >= 0 ? 'at its one-year high' : `${pct(e.hi)} from its one-year high`, e.ma ? 'above its 200-day line' : 'below its 200-day line']
  : [`近半年 ${pct(e.m6)}`, e.hi >= 0 ? '在一年高点' : `距一年高点 ${pct(e.hi)}`, e.ma ? '在 200 日线上方' : '在 200 日线下方'];
}

export type Part = string | {b: string};
export type Row = {tone: Tone; key: string; title: string; note: string; symbols: string[]; more: string; href: string};
const LIGHT: Record<string, [string, string]> = {red: ['红', 'red'], amber: ['黄', 'amber'], green: ['绿', 'green']};

// "What SV saw today": one sentence and a few rows of tickers, all counted from the index.
export function findings(index: StockIndex, en: boolean): {summary: Part[]; rows: Row[]} {
 const s = index.stocks, keys = Object.keys(s);
 const ranked = keys.filter(k => (s[k].mf ?? 0) > 0).sort((a, b) => s[a].mf! - s[b].mf!);
 const byActivity = (state: Shape) => keys.filter(k => s[k].sh === state).sort((a, b) => (s[a].a ?? 999) - (s[b].a ?? 999) || a.localeCompare(b));
 const broken = byActivity('broken_out'), waiting = byActivity('waiting');
 const calm = index.big.filter(k => s[k] && !busy(s[k]));
 const fresh = [...new Set([...index.new.w3, ...index.new.mf, ...index.new.sh])];
 const w3 = index.w3, light = w3.light ? LIGHT[w3.light] : null, blocked = !!light && w3.light !== 'green';
 const latest = w3.latest.filter(k => s[k]), unordered = latest.length > 0 && latest.every(k => s[k].w3?.status === 'skipped');
 const summary: Part[] = en ? [
  ...(fresh.length ? [{b: `${fresh.length} new`}, ` since ${md(index.new_since)}. `] : []),
  {b: `${index.mf_triggered}`}, ' stocks triggered the multi-factor scan', ...(ranked.length ? ['; ', {b: ranked[0]}, ' ranks first'] : []), '. ',
  'Of the ', `${index.shape_watch ?? 100}`, ' most-traded, ', {b: `${broken.length}`}, ' setups have broken out and ', {b: `${waiting.length}`}, ' are waiting. ',
  '3W: ', w3.new ? {b: `${w3.new} new signals`} : {b: 'no new signal'}, ` in the week of ${md(w3.week)}`, blocked ? `; the market light is ${light![1]}, so signals would not be ordered` : '', '. ',
  ...(calm.length ? [`${calm.slice(0, 3).join(', ')} and other big names: nothing today.`] : []),
 ] : [
  ...(fresh.length ? [`和 ${md(index.new_since)} 比，今天新出现 `, {b: `${fresh.length}`}, ' 只。'] : []),
  '多因子 ', {b: `${index.mf_triggered}`}, ' 只触发', ...(ranked.length ? ['，', {b: ranked[0]}, ' 排第一'] : []), '。',
  `成交最活跃的 ${index.shape_watch ?? 100} 只里，`, {b: `${broken.length}`}, ' 只形态已突破、', {b: `${waiting.length}`}, ' 只在等突破。',
  `3W ${md(w3.week)} 那周`, w3.new ? {b: `出了 ${w3.new} 个新信号`} : {b: '没有新信号'}, blocked ? `，市场灯${light![0]}，有信号也不会下单` : '', '。',
  ...(calm.length ? [`${calm.slice(0, 3).join('、')} 等大票今天都没有动静。`] : []),
 ];
 const rows: Row[] = [];
 if (fresh.length) rows.push({tone: 'go', key: 'new', title: en ? 'New today' : '今天新出现', note: en ? `vs ${md(index.new_since)}` : `和 ${md(index.new_since)} 比`, symbols: fresh.slice(0, 10), more: '', href: ''});
 rows.push({tone: 'go', key: 'mf', title: en ? 'Multi-factor candidates' : '多因子候选', note: en ? `Top 5 of ${ranked.length}` : `前 5 · 共 ${ranked.length} 只`, symbols: ranked.slice(0, 5), more: '', href: '/multi-factor'});
 if (broken.length) rows.push({tone: 'go', key: 'broken', title: en ? 'Setups broken out' : '形态已突破', note: en ? `${broken.length} stocks` : `${broken.length} 只`, symbols: broken.slice(0, 8), more: broken.length > 8 ? (en ? `${broken.length - 8} more` : `还有 ${broken.length - 8} 只`) : '', href: '/patterns'});
 if (waiting.length) rows.push({tone: 'wait', key: 'waiting', title: en ? 'Setups waiting' : '形态在等突破', note: en ? `${waiting.length} · by dollar volume` : `${waiting.length} 只 · 按成交额排`, symbols: waiting.slice(0, 6), more: waiting.length > 6 ? (en ? `${waiting.length - 6} more` : `还有 ${waiting.length - 6} 只`) : '', href: '/patterns'});
 rows.push({tone: blocked && w3.light === 'red' ? 'stop' : 'off', key: 'w3', title: en ? '3W weekly rule' : '3W 周线规则',
  note: w3.new ? (en ? `${w3.new} new in the week of ${md(w3.week)}` : `${md(w3.week)} 那周 ${w3.new} 个新信号`) : (en ? `No new signal in the week of ${md(w3.week)}` : `${md(w3.week)} 那周没有新信号`),
  symbols: latest, more: latest.length ? (en ? `latest batch, week of ${md(w3.latest_week)}${unordered ? ' · none ordered' : ''}` : `最近一批 · ${md(w3.latest_week)} 那周${unordered ? ' · 都没下单' : ''}`) : '', href: '/signals'});
 if (calm.length) rows.push({tone: 'off', key: 'big', title: en ? 'Big names' : '大票', note: en ? 'Most traded today · nothing happening' : '今天成交额最大 · 三项都没动静', symbols: calm.slice(0, 8), more: '', href: ''});
 return {summary, rows};
}
