import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {loadTs} from './helpers/load-ts.mjs';
const {LocaleProvider}=loadTs('app/i18n/locale.tsx');
const learn=loadTs('app/learn/learn.tsx');
const render=locale=>renderToStaticMarkup(React.createElement(LocaleProvider,{initialLocale:locale},React.createElement(learn.LearnView)));
const visible=html=>html.replace(/<[^>]*>/g,'');

test('learn page: four steps, glossary, costs and tax, every source linked',()=>{
 const zh=render('zh');
 assert.equal(learn.steps.length,4);
 // The four steps are drawn by the stepper (terminal.tsx); the view keeps the folded detail.
 assert.ok(learn.steps.every(([title,body])=>title&&body&&body.length<=90),'each step is short');
 for(const [term] of learn.glossary)assert.ok(zh.includes(term));
 for(const [,href] of learn.sources)assert.ok(zh.includes(`href="${href}"`));
 assert.ok(zh.includes('不是投资或税务建议'));
 assert.ok(zh.includes('2026-10-24'));
});

test('learn page renders fully in English with the same numbers',()=>{
 const en=render('en'),zh=render('zh');
 assert.doesNotMatch(visible(en),/[㐀-鿿]/);
 for(const m of en.matchAll(/(?:aria-label|title)="([^"]*)"/g))assert.doesNotMatch(m[1],/[㐀-鿿]/);
 const numbers=html=>[...visible(html).matchAll(/US\$[\d.,]*\d|\$[\d.,]*\d|\d+(?:\.\d+)?%|20\d\d-\d\d-\d\d/g)].map(m=>m[0]);
 assert.deepEqual(numbers(en),numbers(zh));
});
