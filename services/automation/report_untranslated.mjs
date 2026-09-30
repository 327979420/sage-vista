// Report (never fail) Chinese text left on the English pages by today's data.
// New data can produce wording the catalog has not seen yet; that must be visible
// to fix, but it must not block a correct daily release.
import {appendFileSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {loadTs} from '../../tests/helpers/load-ts.mjs';

const CJK = /[\u3400-\u9fff][^<>\n]{0,40}/g;

export function untranslated(html) {
 const visible = html.replace(/<(script|style)[\s\S]*?<\/\1>/g, '').replace(/<[^>]*>/g, '\n');
 const attributes = [...html.matchAll(/(?:aria-label|title|placeholder|alt)="([^"]*)"/g)].map(m => m[1]).join('\n');
 const found = new Set();
 for (const text of [visible, attributes]) for (const match of text.matchAll(CJK)) found.add(match[0].trim());
 found.delete('中文'); // the language switch label is Chinese by design
 return [...found];
}

export function reportPublic(publicDir = 'public') {
 const read = name => JSON.parse(readFileSync(path.join(publicDir, `${name}.json`), 'utf8'));
 const {LocaleProvider} = loadTs('app/i18n/locale.tsx');
 const render = (component, props) => renderToStaticMarkup(React.createElement(LocaleProvider, {initialLocale: 'en'}, React.createElement(component, props)));
 const sample = read('market-internals'), candidates = read('cr056-ranking');
 const views = {
  Market: () => render(loadTs('app/zh/watch/market/dashboard.tsx').MarketView, {cockpit: read('market-cockpit'), sample, targetDate: sample.as_of}),
  Sectors: () => render(loadTs('app/zh/watch/industry-radar/dashboard.tsx').IndustryView, {context: read('industry-radar').display_context, targetDate: sample.as_of, candidates: candidates.ranked_symbols, candidateDate: candidates.as_of}),
  'Multi-factor opportunities': () => render(loadTs('app/zh/watch/resonance/rare-opportunities/cr056-ranking.tsx').CandidateView, {data: candidates, latestDate: candidates.as_of}),
  'Daily setups': () => render(loadTs('app/zh/watch/resonance/favorite-pattern/page.tsx').DailyPatternView, {data: read('daily-shape-picker'), onRetry: () => {}}),
 };
 return Object.entries(views).map(([page, view]) => {
  try { return {page, fragments: untranslated(view())}; }
  catch (error) { return {page, fragments: [], error: String(error.message ?? error)}; }
 });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
 const results = reportPublic(process.argv[2] ?? 'public');
 const lines = [];
 for (const {page, fragments, error} of results) {
  if (error) lines.push(`${page}: could not render for the English check (${error})`);
  for (const fragment of fragments) lines.push(`${page}: untranslated "${fragment}"`);
 }
 console.log(lines.length ? lines.join('\n') : 'English pages: no untranslated text in today\'s data.');
 for (const line of lines) console.log(`::warning title=Untranslated text::${line}`);
 if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, `\n### English coverage\n\n${lines.length ? lines.map(l => `- ${l}`).join('\n') : 'No untranslated text in today\'s data.'}\n`);
}
