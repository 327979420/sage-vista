import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import yaml from 'js-yaml';

const workflow = yaml.load(readFileSync(new URL('../.github/workflows/m12-publication-authorize.yml', import.meta.url), 'utf8'));

test('authorization workflow stays disabled with no caller inputs or automatic triggers', () => {
  assert.deepEqual(Object.keys(workflow).sort(), ['jobs', 'name', 'on', 'permissions']);
  assert.deepEqual(workflow.on, { workflow_dispatch: null });
  assert.deepEqual(workflow.permissions, { contents: 'read' });
  assert.deepEqual(Object.keys(workflow.jobs), ['validate']);
  const job = workflow.jobs.validate;
  assert.deepEqual(Object.keys(job).sort(), ['environment', 'if', 'permissions', 'runs-on', 'steps', 'timeout-minutes']);
  assert.equal(job.if, '${{ false }}');
  assert.equal(job.environment, 'production');
  assert.equal(job['runs-on'], 'ubuntu-24.04');
  assert.equal(job['timeout-minutes'], 15);
  assert.deepEqual(job.permissions, { contents: 'read', 'id-token': 'write' });
  const config = JSON.parse(readFileSync(new URL('../config/publication-authorization-runtime.json', import.meta.url)));
  assert.deepEqual(config, { protocol: 'm12-authorization-runtime/1', enabled: false, coordinator_origin: null });
});

test('only pinned checkout, pinned Python and fixed isolated entry execute', () => {
  const steps = workflow.jobs.validate.steps;
  assert.equal(steps.length, 3);
  assert.deepEqual(steps.map(step => { const rest = { ...step }; delete rest.name; return rest; }), [
    { uses: 'actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd',
      with: { ref: '${{ github.sha }}', 'persist-credentials': false, 'fetch-depth': 1, submodules: false, lfs: false } },
    { uses: 'actions/setup-python@e797f83bcb11b83ae66e0230d6156d7c80228e7c',
      with: { 'python-version': '3.12.12', architecture: 'x64', 'check-latest': false } },
    { shell: 'bash', run: 'python -I -B "$GITHUB_WORKSPACE/services/publication/authorization_runtime.py"' },
  ]);
});
