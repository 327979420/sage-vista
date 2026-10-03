import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {loadTs} from './helpers/load-ts.mjs';
const {TOUR_STEPS, TOUR_COPY, TOUR_SEEN_KEY, tourSeen} = loadTs('app/tour-steps.ts');

test('each tour step is one short sentence in both languages, with a screenshot', () => {
 assert.deepEqual(TOUR_STEPS.map(s => s.id), ['multi-factor', 'search', 'daily-setups', 'market-sectors']);
 for (const step of TOUR_STEPS) {
  for (const lang of ['en', 'zh']) {
   const text = step.text[lang];
   assert.ok(step.title[lang] && text, `${step.id} ${lang}`);
   assert.equal((text.match(/[.?!。？！]/g) ?? []).length, 1, `${step.id} ${lang} should be one sentence: ${text}`);
   assert.ok(text.length <= (lang === 'en' ? 100 : 40), `${step.id} ${lang} too long`);
   const image = `public/tour/${lang}/${step.image}.webp`;
   assert.ok(fs.existsSync(image) && fs.statSync(image).size < 150_000, image);
  }
 }
 for (const [key, value] of Object.entries(TOUR_COPY)) assert.ok(value.en && value.zh, key);
});

test('the tour shows once per browser and never uses anything but the local marker', () => {
 assert.equal(tourSeen('', null), false);
 assert.equal(tourSeen('sv-language-session=zh', null), false);
 assert.equal(tourSeen(`a=b; ${TOUR_SEEN_KEY}=1`, null), true);
 assert.equal(tourSeen('', '1'), true);
 assert.equal(tourSeen(`${TOUR_SEEN_KEY}=0`, null), false);
});
