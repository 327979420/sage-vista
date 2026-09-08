import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const source=fs.readFileSync(new URL('../app/zh/watch/resonance/strategy-backtest-v2/research-runs.tsx',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const mod={exports:{}};new Function('require','exports','module',code)(createRequire(import.meta.url),mod.exports,mod);
const {checkedIndex,ResearchRunList,default:ResearchRuns}=mod.exports;
test('fixed result paths reject arbitrary report identities and malformed index',()=>{
 const run={id:'123-1',status:'failed',request:{start:'2026-01-01',end:'2026-02-01'},summary:{},receipt_sha256:'a'.repeat(64)};
 assert.equal(checkedIndex({schema_version:'legacy-research-index-v1',runs:[run]}).length,1);
 for(const patch of [{id:'../../outside'}, {status:'validated'},{receipt_sha256:'bad'},{summary:{total_return:'wrong'}},{summary:{max_drawdown:{}}},{request:{start:{}}}])assert.throws(()=>checkedIndex({schema_version:'legacy-research-index-v1',runs:[{...run,...patch}]}));
 const markup=renderToStaticMarkup(React.createElement(ResearchRunList,{runs:[run],selected:'',onSelect:()=>{}}));
 assert.match(markup,/运行失败/);assert.match(markup,/不可用/);assert.doesNotMatch(markup,/0\.00%/);
});
test('pending account scenario has no fake runnable entry and HTML is sandboxed',()=>{
 const markup=renderToStaticMarkup(React.createElement(ResearchRuns));
 assert.match(markup,/账户运行待参数确认/);assert.match(markup,/<button disabled/);
 assert.doesNotMatch(markup,/research-backtest\.yml/);
 assert.match(source,/sandbox=""/);assert.match(source,/img-src data:/);assert.doesNotMatch(source,/allow-scripts|allow-same-origin/);
});

test('manual input-check workflow cannot compute, deploy or expose a token',async()=>{
 const yaml=(await import('js-yaml')).default;
 const workflow=yaml.load(fs.readFileSync(new URL('../.github/workflows/research-backtest.yml',import.meta.url),'utf8'));
 assert.deepEqual(Object.keys(workflow.on),['workflow_dispatch']);
 assert.match(workflow.jobs.preflight.if,/refs\/heads\/main/);
 assert.deepEqual(workflow.jobs.preflight.steps.find(s=>s.env)?.env,{RESEARCH_INPUTS:'${{ toJSON(inputs) }}'});
 const body=JSON.stringify(workflow);
 assert.doesNotMatch(body,/pip install|vectorbt_comparison|quantstats_report|deploy-site|secrets\./);
 assert.match(body,/publish_attempt/);assert.match(body,/exit 1/);
});
