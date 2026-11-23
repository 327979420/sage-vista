import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {loadTs} from './helpers/load-ts.mjs';
const {TOUR_STEPS, TOUR_COPY, TOUR_SEEN_KEY, tourSeen} = loadTs('app/tour-steps.ts');

test('start-here lists four real pages, one short line each in both languages', () => {
 assert.deepEqual(TOUR_STEPS.map(s => s.href), ['/', '/signals', '/forward', '/learn']);
 const nav = fs.readFileSync('app/site-navigation.tsx', 'utf8');
 for (const step of TOUR_STEPS) {
  assert.ok(nav.includes(`'${step.href}'`), `${step.href} is a menu page`);
  for (const lang of ['en', 'zh']) {
   const text = step.text[lang];
   assert.ok(step.title[lang] && text, `${step.id} ${lang}`);
   assert.equal((text.match(/[.?!。？！]/g) ?? []).length, 1, `${step.id} ${lang} should be one sentence: ${text}`);
   assert.ok(text.length <= (lang === 'en' ? 60 : 20), `${step.id} ${lang} too long`);
  }
 }
 for (const [key, value] of Object.entries(TOUR_COPY)) assert.ok(value.en && value.zh, key);
});

test('no crow guide or full-screen welcome remains', () => {
 for (const file of ['app/crow.tsx', 'app/crow-art.tsx', 'app/tour.tsx']) assert.ok(!fs.existsSync(file), file);
 const layout = fs.readFileSync('app/layout.tsx', 'utf8');
 assert.doesNotMatch(layout, /Crow|<Tour/);
});

test('the start-here pulse shows once per browser and never uses anything but the local marker', () => {
 assert.equal(tourSeen('', null), false);
 assert.equal(tourSeen('sv-language-session=zh', null), false);
 assert.equal(tourSeen(`a=b; ${TOUR_SEEN_KEY}=1`, null), true);
 assert.equal(tourSeen('', '1'), true);
 assert.equal(tourSeen(`${TOUR_SEEN_KEY}=0`, null), false);
});
