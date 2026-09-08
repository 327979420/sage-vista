import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import yaml from 'js-yaml';
const root=new URL('../',import.meta.url);

test('comparison mode is isolated from all legacy refresh and production actions',()=>{
 const workflow=yaml.load(fs.readFileSync(new URL('.github/workflows/opportunity-ledger-refresh.yml',root),'utf8'));
 assert.equal(workflow.on.workflow_dispatch.inputs.mode.default,'refresh');
 assert.match(workflow.jobs.refresh.if,/inputs.mode == 'refresh'/);
 const job=workflow.jobs.comparison;
 assert.match(job.if,/workflow_dispatch.*inputs.mode == 'comparison'/);
 assert.deepEqual(job.permissions,{contents:'read',actions:'read'});
 assert.deepEqual(job.strategy.matrix.include.map(x=>x.cache_key),['eodhd-history-v1-33293559230','eodhd-history-v1-34184997473']);
 const restore=job.steps.find(x=>x.uses==='actions/cache/restore@v4');
 assert.equal(restore.with['fail-on-cache-miss'],true);assert.equal(restore.with['restore-keys'],undefined);
 assert.ok(!JSON.stringify(job).includes('secrets.'));assert.ok(!JSON.stringify(job).includes('actions/cache/save'));
 assert.ok(!JSON.stringify(job).includes('git push'));assert.ok(!JSON.stringify(job).includes('deploy-site'));
 const upload=job.steps.find(x=>x.uses==='actions/upload-artifact@v4');
 assert.equal(upload.with.path,'work/vectorbt-derived/*.json');
});

test('real comparison report renders differences, costs and path limitations',()=>{
 const source=fs.readFileSync(new URL('app/zh/backtest/comparison.tsx',root),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const mod={exports:{}};new Function('require','exports','module',code)(createRequire(import.meta.url),mod.exports,mod);
 const {reports}=JSON.parse(fs.readFileSync(new URL('public/vectorbt-comparison.json',root),'utf8'));
 const html=renderToStaticMarkup(React.createElement(mod.exports.ComparisonView,{reports}));
 assert.match(html,/平均每笔毛收益/);assert.match(html,/\+5\.73%/);assert.match(html,/70%/);assert.match(html,/3\.95/);assert.match(html,/这不是完整回测/);assert.match(html,/有差异/);assert.match(html,/真实费用与数量缺失/);
 assert.match(html,/MFE／MAE/);assert.match(html,/VectorBT没有重新决定买卖/);assert.match(html,/原始差值/);
 assert.equal((html.match(/data-selected=/g)||[]).length,20);
 assert.doesNotMatch(html,/adjusted_close|api_token/);
});
