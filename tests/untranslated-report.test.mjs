import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fixture} from './helpers/public-fixture.mjs';
import {reportPublic, untranslated} from '../services/automation/report_untranslated.mjs';

function bundle(t, edit = () => {}) {
 const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sv-english-'));
 t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
 const assets = Object.fromEntries(['market-internals', 'market-cockpit', 'industry-radar', 'cr056-ranking', 'daily-shape-picker'].map(name => [name, fixture(name)]));
 edit(assets);
 for (const [name, value] of Object.entries(assets)) fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(value));
 return dir;
}

test('finds Chinese text and attributes but ignores the language switch label', () => {
 assert.deepEqual(untranslated('<p>Market</p><button>中文</button><span title="新提示">ok</span><b>等权, 小盘更弱</b>'), ['等权, 小盘更弱', '新提示']);
});

test('every page renders in English for the frozen release', t => {
 const results = reportPublic(bundle(t));
 assert.deepEqual(results.map(r => r.page), ['Market', 'Sectors', 'Multi-factor opportunities', 'Daily setups']);
 for (const r of results) assert.deepEqual({page: r.page, error: r.error, fragments: r.fragments}, {page: r.page, error: undefined, fragments: []});
});

test('new untranslated data wording is reported, not thrown', t => {
 const dir = bundle(t, assets => {
  const first = assets['cr056-ranking'].continuing_ranked_symbols[0];
  assets['cr056-ranking'].reviews.find(r => r.symbol === first).reason_codes = ['全新的未翻译原因'];
 });
 const page = reportPublic(dir).find(r => r.page === 'Multi-factor opportunities');
 assert.ok(page.fragments.includes('全新的未翻译原因'), page.fragments);
});
