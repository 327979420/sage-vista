import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ARTIFACT_NAME, PAGES, VIEWPORTS, TOUR_SEEN_KEY, previewOrigin, previewUrlFromLog} from '../scripts/site-preview-screenshots.mjs';
const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

test('preview captures six pages at the two review sizes', () => {
  assert.deepEqual(PAGES, [
    {name: 'today', path: '/'},
    {name: 'portfolio', path: '/portfolio'},
    {name: 'signals', path: '/signals'},
    {name: 'forward', path: '/forward'},
    {name: 'patterns', path: '/patterns'},
    {name: 'reference', path: '/zh/watch/resonance/rare-opportunities'},
  ]);
  assert.deepEqual(VIEWPORTS, [{width: 1440, height: 900}, {width: 390, height: 844}]);
  assert.equal(new Set(PAGES.flatMap(p => VIEWPORTS.map(v => `${p.name}-${v.width}x${v.height}.png`))).size, 12);
});
test('tour bypass matches the current app flag and screenshot version is exactly locked', () => {
  assert.ok(read('app/tour-steps.ts').includes(`TOUR_SEEN_KEY = '${TOUR_SEEN_KEY}'`));
  const pkg = JSON.parse(read('package.json')), lock = JSON.parse(read('package-lock.json'));
  assert.equal(pkg.devDependencies.playwright, '1.63.0');
  assert.equal(lock.packages[''].devDependencies.playwright, pkg.devDependencies.playwright);
  assert.equal(lock.packages['node_modules/playwright'].version, pkg.devDependencies.playwright);
});
test('deploy URL resolution accepts only the fixed preview worker and rejects ambiguity', () => {
  const url = 'https://sv-preview.example.workers.dev';
  assert.equal(previewUrlFromLog(`Uploaded\n${url}\n${url}`), url);
  for (const value of ['https://sage.freddyliang.com', 'https://other.example.workers.dev', `${url}/portfolio`, 'http://sv-preview.example.workers.dev', `${url}?x=y`, 'https://sv-preview.example.workers.dev.evil.test']) assert.throws(() => previewOrigin(value));
  assert.throws(() => previewUrlFromLog('no URL'));
  assert.throws(() => previewUrlFromLog(`${url}\nhttps://sv-preview.another.workers.dev`));
});
test('workflow installs Chromium after deploy and uploads diagnostics even on capture failure', () => {
  const workflow = read('.github/workflows/preview-site.yml');
  assert.ok(workflow.indexOf('wrangler deploy') < workflow.indexOf('playwright install --with-deps chromium'));
  assert.ok(workflow.includes('node scripts/site-preview-screenshots.mjs "$PREVIEW_URL"'));
  assert.ok(workflow.includes(`name: ${ARTIFACT_NAME}`));
  assert.ok(workflow.includes('always() && steps.preview-address.outputs.url'));
});
