import { test } from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import { previewConfig } from '../scripts/site-preview-config.mjs';
const build = { main: 'index.js', compatibility_date: '2026-10-01', assets: { directory: '../client', binding: 'ASSETS' }, routes: [{ pattern: 'sage.freddyliang.com', custom_domain: true }], name: 'sage-vista-parallel', secrets: { required: ['SECRET'] }, triggers: { crons: ['* * * * *'] }, r2_buckets: [{}], vars: { secret: 'no' }, services: [{}] };
test('preview rejects main, tags, missing identity and malformed run IDs', () => {
  for (const ref of ['refs/heads/main', 'refs/tags/v2', undefined]) assert.throws(() => previewConfig(build, ref, '123'));
  for (const id of ['', '../prod', undefined]) assert.throws(() => previewConfig(build, 'refs/heads/site/v2', id));
});
test('preview strips production routes, bindings, variables and schedules', () => {
  const config = previewConfig(build, 'refs/heads/site/v2', '123');
  assert.equal(config.name, 'sv-preview');
  assert.deepEqual(config.routes, []);
  for (const key of ['secrets', 'triggers', 'r2_buckets', 'vars', 'services']) assert.equal(key in config, false);
  assert.equal(config.main, build.main);
  assert.equal(config.assets.directory, build.assets.directory);
  assert.equal(build.name, 'sage-vista-parallel');
  assert.throws(() => previewConfig({}, 'refs/heads/site/v2', '123'));
});

test('every dispatch shares one isolated worker', () => {
 assert.equal(previewConfig(build, 'refs/heads/site/v2', '123').name, previewConfig(build, 'refs/heads/another', '456').name);
});

test('preview dispatch is serialized across branches and remains manual and non-main', () => {
 const workflow=readFileSync(new URL('../.github/workflows/preview-site.yml',import.meta.url),'utf8');
 assert.match(workflow,/group: site-preview\n/);
 assert.match(workflow,/cancel-in-progress: false/);
 assert.match(workflow,/github.event_name == 'workflow_dispatch'/);
 assert.match(workflow,/github.ref != 'refs\/heads\/main'/);
 assert.doesNotMatch(workflow,/\n {2}(push|schedule|pull_request):/);
 assert.match(workflow,/wrangler deploy --config dist\/server\/wrangler.preview.json/);
});
