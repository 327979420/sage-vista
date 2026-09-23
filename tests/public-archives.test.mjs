import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { gzipSync, gunzipSync } from 'node:zlib';
import { randomBytes } from 'node:crypto';
import { packageArchives, policy } from '../services/automation/package_public_archives.mjs';
import { loadTs } from './helpers/load-ts.mjs';

const { servePublicArchive } = loadTs(new URL('../worker/public-archives.ts', import.meta.url));

function fixture(t, content) {
  const dir = mkdtempSync(path.join(tmpdir(), 'sv-archives-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const source = path.join(dir, 'public'), destination = path.join(dir, 'dist');
  mkdirSync(source); mkdirSync(destination);
  for (const name of policy.archives) {
    writeFileSync(path.join(source, name), content);
    writeFileSync(path.join(destination, name), content);
  }
  return { source, destination };
}

test('large raw histories retain every byte while deployment fits the limit', t => {
  const original = Buffer.from(JSON.stringify({ evidence: '历史数据'.repeat(2_300_000) }));
  assert.ok(original.length > policy.maxAssetBytes);
  const { source, destination } = fixture(t, original);
  const result = packageArchives(source, destination);
  for (const { name, deployedBytes } of result) {
    assert.ok(deployedBytes < policy.maxAssetBytes);
    assert.deepEqual(readFileSync(path.join(source, name)), original);
    assert.deepEqual(gunzipSync(readFileSync(path.join(destination, policy.assetPrefix, `${name}.gz`))), original);
    assert.equal(existsSync(path.join(destination, name)), false);
  }
});

test('oversize compressed payload and stale builds fail before removing originals', t => {
  const { source, destination } = fixture(t, randomBytes(4096));
  assert.throws(() => packageArchives(source, destination, 100), /Hosting limit/);
  for (const name of policy.archives) assert.deepEqual(readFileSync(path.join(source, name)), readFileSync(path.join(destination, name)));
  writeFileSync(path.join(destination, policy.archives[0]), 'stale');
  assert.throws(() => packageArchives(source, destination), /Build\/source mismatch/);
});

test('archive route preserves JSON bytes for gzip, identity, default and HEAD clients', async () => {
  const original = Buffer.from(JSON.stringify({ date: '2026-09-22', score: 58.85, text: '保留全部历史' }));
  for (const name of policy.archives) {
    for (const [encoding, gzip] of [['gzip, br', true], ['GZIP; q=0.7', true], ['*', true], ['gzip;q=0, *;q=1', false], ['identity', false], ['', false]]) {
      const assets = { async fetch(request) {
        assert.equal(new URL(request.url).pathname, `${policy.assetPrefix}${name}.gz`);
        assert.equal(new URL(request.url).search, '?v=latest');
        assert.equal(request.headers.get('Accept-Encoding'), 'identity');
        assert.equal(request.headers.get('Range'), null);
        assert.equal(request.headers.get('If-None-Match'), null);
        return new Response(gzipSync(original), { headers: { 'Content-Type': 'application/gzip', ETag: 'internal' } });
      } };
      const request = new Request(`https://sv.test/${name}?v=latest`, { headers: { 'Accept-Encoding': encoding, Range: 'bytes=0-5', 'If-None-Match': 'old' } });
      const response = await servePublicArchive(request, assets);
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('Content-Encoding'), gzip ? 'gzip' : null);
      assert.equal(response.headers.get('ETag'), null);
      assert.equal(response.headers.get('Vary'), 'Accept-Encoding');
      const bytes = Buffer.from(await response.arrayBuffer());
      assert.deepEqual(gzip ? gunzipSync(bytes) : bytes, original);
      const head = await servePublicArchive(new Request(request, { method: 'HEAD' }), assets);
      assert.equal(await head.text(), '');
      assert.equal(head.headers.get('Content-Encoding'), gzip ? 'gzip' : null);
    }
  }
});

test('unknown routes pass through; missing archives fail clearly; development can use raw JSON', async () => {
  const noAssets = { fetch: async () => { throw new Error('unexpected fetch'); } };
  assert.equal(await servePublicArchive(new Request('https://sv.test/other.json'), noAssets), null);
  assert.equal((await servePublicArchive(new Request('https://sv.test/signal-history.json', { method: 'POST' }), noAssets)).status, 405);
  const missing = { fetch: async () => new Response('missing', { status: 404 }) };
  assert.equal((await servePublicArchive(new Request('https://sv.test/signal-history.json'), missing)).status, 503);
  const dev = { fetch: async r => new URL(r.url).pathname.includes('__sv_archives') ? new Response(null, { status: 404 }) : new Response('{"ok":true}', { headers: { 'Content-Type': 'application/json' } }) };
  assert.deepEqual(await (await servePublicArchive(new Request('https://sv.test/signal-history.json'), dev)).json(), { ok: true });
});

test('production build packages the actual public archives byte for byte', () => {
  for (const name of policy.archives) {
    const compressed = readFileSync(path.join('dist/client', policy.assetPrefix, `${name}.gz`));
    assert.ok(compressed.length <= policy.maxAssetBytes);
    assert.deepEqual(gunzipSync(compressed), readFileSync(path.join('public', name)));
    assert.equal(existsSync(path.join('dist/client', name)), false);
  }
});
