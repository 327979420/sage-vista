import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { checkPublicSizes, formatReport, RAW_LIMIT_BYTES } from '../services/automation/check_public_sizes.mjs';

const archives = ['big-archive.json'];

function publicDir(t, files) {
  const dir = mkdtempSync(path.join(tmpdir(), 'sv-sizes-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    writeFileSync(path.join(dir, name), content);
  }
  return dir;
}

test('raw limit is 20 MiB, below the 25 MiB Cloudflare limit', () => {
  assert.equal(RAW_LIMIT_BYTES, 20 * 1024 * 1024);
});

test('unlisted file above the raw limit fails with a clear message, including nested paths', t => {
  const dir = publicDir(t, { 'big-archive.json': '{}', 'nested/huge.json': Buffer.alloc(101), 'small.json': Buffer.alloc(100) });
  const result = checkPublicSizes(dir, { archives, maxAssetBytes: 1000, rawLimit: 100 });
  assert.equal(result.ok, false);
  assert.equal(result.errors.length, 1);
  assert.match(result.errors[0], /^public\/nested\/huge\.json is .* not listed in services\/automation\/public-archive-policy\.json/);
});

test('listed archive above the raw limit passes and reports compressed headroom', t => {
  const dir = publicDir(t, { 'big-archive.json': JSON.stringify({ rows: 'x'.repeat(5000) }), 'small.json': '{}' });
  const result = checkPublicSizes(dir, { archives, maxAssetBytes: 1000, rawLimit: 100 });
  assert.equal(result.ok, true);
  const [report] = result.archives;
  assert.equal(report.name, 'big-archive.json');
  assert.ok(report.rawBytes > 5000);
  assert.ok(report.compressedBytes < 1000);
  assert.equal(report.headroomBytes, 1000 - report.compressedBytes);
  assert.equal(report.percentOfLimit, Number((report.compressedBytes / 10).toFixed(1)));
  assert.equal(report.status, 'ok');
  assert.match(formatReport(result), /\[OK\] big-archive\.json: .* raw -> .* gzip = .*% of .* \(headroom .*\)/);
});

test('archive near or over the limit after compression is flagged', t => {
  const incompressible = randomBytes(900);
  const dir = publicDir(t, { 'big-archive.json': incompressible });
  const near = checkPublicSizes(dir, { archives, maxAssetBytes: 1100, rawLimit: 100 });
  assert.equal(near.ok, true);
  assert.equal(near.archives[0].status, 'warn');
  const over = checkPublicSizes(dir, { archives, maxAssetBytes: 500, rawLimit: 100 });
  assert.equal(over.ok, false);
  assert.equal(over.archives[0].status, 'over');
  assert.match(over.errors[0], /big-archive\.json is .* after gzip, above the .* Cloudflare per-file limit/);
});

test('CLI exits non-zero and prints the error for an oversize unlisted file', t => {
  const dir = publicDir(t, { 'unified-v2-rankings.json': '{}', 'signal-history.json': '{}', 'opportunity-ledger.json': '{}' });
  const script = fileURLToPath(new URL('../services/automation/check_public_sizes.mjs', import.meta.url));
  const pass = spawnSync(process.execPath, [script, dir], { encoding: 'utf8', env: { ...process.env, GITHUB_STEP_SUMMARY: '' } });
  assert.equal(pass.status, 0, pass.stderr);
  assert.match(pass.stdout, /\[OK\] unified-v2-rankings\.json/);
  writeFileSync(path.join(dir, 'market-cockpit.json'), Buffer.alloc(RAW_LIMIT_BYTES + 1));
  const fail = spawnSync(process.execPath, [script, dir], { encoding: 'utf8', env: { ...process.env, GITHUB_STEP_SUMMARY: '' } });
  assert.equal(fail.status, 1);
  assert.match(fail.stdout, /ERROR: public\/market-cockpit\.json is 20\.00 MiB, above the 20\.00 MiB pre-deploy limit/);
});

test('the repository public directory passes the pre-deploy size check', () => {
  const result = checkPublicSizes('public');
  assert.deepEqual(result.errors, []);
});
