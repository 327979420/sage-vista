import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './helpers/load-ts.mjs';
const {classify, suggest, lights, findings, priceFacts, validIndex, stockHref} = loadTs('app/stock/lookup.ts');

const index = {
 schema_version: 1, as_of: '2026-11-23', count: 1660, mf_triggered: 62, mf_ranked: 30, shape_watch: 100, shape_counts: {},
 w3: {as_of: '2026-11-20', week: '2026-11-20', new: 0, light: 'red', latest_week: '2026-11-06', latest: ['SHLS'], since_lock: 17},
 rule: {min_close: 5, min_dollar_volume: 10000000, min_sessions: 420}, closed: 0,
 big: ['NVDA', 'ZS', 'MSFT'], new: {mf: ['FELE'], sh: ['ZS'], w3: []}, new_since: '2026-11-20',
 stocks: {
  NVDA: {c: 182.1, m6: 12.34, hi: -8.1, ma: true},
  NVR: {c: 7100, w3: {id: 'n1', week: '2026-11-06', status: 'skipped'}},
  MSFT: {c: 480, m6: -2, hi: 0, ma: false},
  FELE: {c: 98.11, mf: 1, h: 9, f: ['macd', 'support']},
  ZS: {c: 229.24, sh: 'broken_out', a: 21, mf: 23, h: 7, f: ['macd']},
  INTC: {c: 59.66, sh: 'waiting', a: 12},
  GOOGL: {c: 282.1, mf: 0},
  SHLS: {c: 10.08, x: true, w3: {id: 's1', week: '2026-11-06', status: 'skipped'}},
  'BRK-B': {c: 500, m6: 1, hi: -1, ma: true},
 }};

test('the index shape is checked before use', () => {
 assert.equal(validIndex(index), true);
 assert.equal(validIndex({...index, schema_version: 2}), false);
 assert.equal(validIndex(null), false);
});

test('input is sorted into tracked, not tracked, other markets and Chinese text', () => {
 assert.deepEqual(classify(' nvda ', index), {kind: 'tracked', symbol: 'NVDA', entry: index.stocks.NVDA});
 assert.equal(classify('BRK.B', index).symbol, 'BRK-B');
 assert.deepEqual(classify('AAPL', index), {kind: 'not_tracked', symbol: 'AAPL'});
 for (const other of ['0700.HK', '600519.SS', '7203.T', '600519']) assert.equal(classify(other, index).kind, 'not_us', other);
 assert.equal(classify('腾讯', index).kind, 'chinese');
 assert.equal(classify('  ', index).kind, 'empty');
 assert.equal(classify('NVDA', null).kind, 'not_tracked');
 assert.equal(stockHref('BRK-B'), '/stock/BRK-B');
});

test('suggestions put the exact ticker first, then stocks with something happening', () => {
 assert.deepEqual(suggest('n', index), ['NVR', 'NVDA']);
 assert.deepEqual(suggest('NVDA', index), ['NVDA']);
 assert.deepEqual(suggest('brk.', index), ['BRK-B']);
 assert.deepEqual(suggest('9', index), []);
});

test('three lights say what each view sees', () => {
 const tones = s => lights(index.stocks[s], index, false).map(l => l.tone);
 assert.deepEqual(tones('NVDA'), ['off', 'off', 'off']);
 assert.deepEqual(tones('ZS'), ['off', 'go', 'go']);
 assert.deepEqual(tones('GOOGL'), ['off', 'off', 'wait']);
 assert.deepEqual(tones('NVR'), ['wait', 'off', 'off']);
 const [w3, , mf] = lights(index.stocks.FELE, index, true);
 assert.equal(w3.note, 'Not among the 17 signals since the rule was locked');
 assert.equal(mf.title, 'Candidate #1 of 30');
 assert.deepEqual(priceFacts(index.stocks.NVDA, false), ['近半年 +12.3%', '距一年高点 -8.1%', '在 200 日线上方']);
 assert.deepEqual(priceFacts(index.stocks.MSFT, true), ['-2.0% over six months', 'at its one-year high', 'below its 200-day line']);
 assert.deepEqual(priceFacts(index.stocks.FELE, true), []);
});

test("today's findings name what is new, what has a signal and which big names are quiet", () => {
 const {summary, rows} = findings(index, false);
 const sentence = summary.map(p => typeof p === 'string' ? p : p.b).join('');
 assert.equal(sentence, '和 11-20 比，今天新出现 2 只。多因子 62 只触发，FELE 排第一。成交最活跃的 100 只里，1 只形态已突破、1 只在等突破。3W 11-20 那周没有新信号，市场灯红，有信号也不会下单。NVDA、MSFT 等大票今天都没有动静。');
 assert.deepEqual(rows.map(r => [r.key, r.symbols]), [['new', ['FELE', 'ZS']], ['mf', ['FELE', 'ZS']], ['broken', ['ZS']], ['waiting', ['INTC']], ['w3', ['SHLS']], ['big', ['NVDA', 'MSFT']]]);
 assert.equal(rows.find(r => r.key === 'w3').tone, 'stop');
 assert.match(rows.find(r => r.key === 'w3').more, /都没下单/);
 const en = findings({...index, new: {mf: [], sh: [], w3: []}, w3: {...index.w3, light: 'green', new: 2}}, true);
 assert.equal(en.rows[0].key, 'mf');
 assert.match(en.summary.map(p => typeof p === 'string' ? p : p.b).join(''), /3W: 2 new signals in the week of 11-20\. /);
});
