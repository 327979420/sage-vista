import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import {loadTs} from './helpers/load-ts.mjs';
const {SEEN_COOKIE, INTRO_HREF, RULE_LOCKED, seenFrom} = loadTs('app/first-visit.ts');

test('no crow guide, welcome modal or start-here panel remains', () => {
 for (const file of ['app/crow.tsx', 'app/crow-art.tsx', 'app/tour.tsx', 'app/start-here.tsx', 'app/tour-steps.ts']) assert.ok(!fs.existsSync(file), file);
 const layout = fs.readFileSync('app/layout.tsx', 'utf8');
 assert.doesNotMatch(layout, /Crow|<Tour/);
});

test('the intro shows until the seen cookie is set, and the reopen link is the home page', () => {
 assert.equal(SEEN_COOKIE, 'sv-seen');
 assert.equal(INTRO_HREF, '/?intro=1');
 assert.equal(seenFrom(undefined), false);
 assert.equal(seenFrom('0'), false);
 assert.equal(seenFrom('1'), true);
 assert.match(RULE_LOCKED, /^\d{4}-\d{2}-\d{2}$/);
});

test('intro text stays short and its buttons go to real pages', () => {
 const hero = fs.readFileSync('app/app/first-visit.tsx', 'utf8');
 const headline = hero.match(/<h1 id="fvTitle">\{en\?'([^']+)':'([^']+)'\}<\/h1>/);
 assert.ok(headline, 'headline');
 assert.ok(headline[1].length <= 60 && headline[2].length <= 20, 'headline stays one short line');
 const nav = fs.readFileSync('app/site-navigation.tsx', 'utf8');
 for (const href of hero.matchAll(/href="(\/[a-z]*)"/g)) assert.ok(nav.includes(`'${href[1]}'`), `${href[1]} is a menu page`);
});
