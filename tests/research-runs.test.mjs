import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const source=fs.readFileSync(new URL('../app/zh/backtest/research-runs.tsx',import.meta.url),'utf8');
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
 assert.match(markup,/正在读取研究配置/);assert.match(markup,/<button disabled/);
 assert.doesNotMatch(markup,/research-backtest\.yml/);
 assert.match(source,/sandbox=""/);assert.match(source,/img-src data:/);assert.doesNotMatch(source,/allow-scripts|allow-same-origin/);
});

test('existing workflow isolates research and requires approval before engines',async()=>{
 const yaml=(await import('js-yaml')).default;
 const workflow=yaml.load(fs.readFileSync(new URL('../.github/workflows/opportunity-ledger-refresh.yml',import.meta.url),'utf8'));
 assert.equal(fs.existsSync(new URL('../.github/workflows/research-backtest.yml',import.meta.url)),false);
 assert.deepEqual(workflow.on.workflow_dispatch.inputs.mode.options,['refresh','comparison','research']);
 assert.match(workflow.jobs.refresh.if,/inputs.mode == 'refresh'/);
 assert.match(workflow.jobs.research.if,/inputs.mode == 'research'/);
 assert.match(workflow.jobs.research.if,/refs\/heads\/main/);
 const steps=workflow.jobs.research.steps;
 assert.match(steps.find(s=>s.id==='approval').run,/run_research --check/);
 assert.match(steps.find(s=>s.name?.startsWith('Install isolated')).if,/approval.outputs.enabled == 'true'/);
 assert.match(steps.find(s=>s.name?.startsWith('Run the selected')).if,/approval.outputs.enabled == 'true'/);
 assert.doesNotMatch(JSON.stringify(workflow.jobs.research),/deploy-site|secrets\.|cache\/save/);
 assert.match(JSON.stringify(workflow.jobs.research),/publish_attempt/);
});


test('trade score lookup requires original event, symbol, day and rank',()=>{
 const t={event_id:'A-1',symbol:'A',signal_date:'2026-01-02',rank:1};
 const map=new Map([['A-1',{symbol:'A',signal_date:t.signal_date,selection:{rank:1,technical_score:5}}]]);
 assert.equal(mod.exports.matchingSignal(t,map).technical_score,5);
 for(const patch of [{event_id:'missing'},{symbol:'B'},{signal_date:'2026-01-03'},{rank:2}])assert.throws(()=>mod.exports.matchingSignal({...t,...patch},map));
});
