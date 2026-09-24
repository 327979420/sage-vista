import { appendFileSync, readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { policy } from './package_public_archives.mjs';

const MiB = 1024 * 1024;
// Early warning well below Cloudflare's 25 MiB per-file hard limit.
export const RAW_LIMIT_BYTES = 20 * MiB;
export const ARCHIVE_WARN_RATIO = 0.8;

function listFiles(folder) {
  return readdirSync(folder).flatMap(name => {
    const file = path.join(folder, name);
    return statSync(file).isDirectory() ? listFiles(file) : [file];
  });
}

const mib = bytes => `${(bytes / MiB).toFixed(2)} MiB`;

// Fail-closed pre-deploy gate: an unlisted public file above RAW_LIMIT_BYTES
// would reach Cloudflare uncompressed, and a listed archive must still fit
// the hosting limit after the same gzip -9 the packager applies.
export function checkPublicSizes(source = 'public', { archives = policy.archives, maxAssetBytes = policy.maxAssetBytes, rawLimit = RAW_LIMIT_BYTES } = {}) {
  const archived = new Set(archives);
  const oversize = listFiles(source)
    .map(file => ({ name: path.relative(source, file).split(path.sep).join('/'), bytes: statSync(file).size }))
    .filter(({ name, bytes }) => bytes > rawLimit && !archived.has(name));
  const report = archives.map(name => {
    const original = readFileSync(path.join(source, name));
    const compressedBytes = gzipSync(original, { level: 9 }).length;
    const ratio = compressedBytes / maxAssetBytes;
    return { name, rawBytes: original.length, compressedBytes, limitBytes: maxAssetBytes, percentOfLimit: Number((ratio * 100).toFixed(1)), headroomBytes: maxAssetBytes - compressedBytes, status: ratio > 1 ? 'over' : ratio >= ARCHIVE_WARN_RATIO ? 'warn' : 'ok' };
  });
  const errors = [
    ...oversize.map(({ name, bytes }) => `public/${name} is ${mib(bytes)}, above the ${mib(rawLimit)} pre-deploy limit, and is not listed in services/automation/public-archive-policy.json. Shrink it or add it to "archives" so it is deployed gzip-compressed.`),
    ...report.filter(item => item.status === 'over').map(({ name, compressedBytes }) => `public/${name} is ${mib(compressedBytes)} after gzip, above the ${mib(maxAssetBytes)} Cloudflare per-file limit.`),
  ];
  return { ok: errors.length === 0, errors, archives: report };
}

export function formatReport({ archives, errors }) {
  const lines = ['Public archive compressed size vs Cloudflare per-file limit:'];
  for (const a of archives) lines.push(`  [${a.status.toUpperCase()}] ${a.name}: ${mib(a.rawBytes)} raw -> ${mib(a.compressedBytes)} gzip = ${a.percentOfLimit}% of ${mib(a.limitBytes)} (headroom ${mib(a.headroomBytes)})`);
  for (const error of errors) lines.push(`ERROR: ${error}`);
  return lines.join('\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = checkPublicSizes(process.argv[2] ?? 'public');
  console.log(formatReport(result));
  if (process.env.GITHUB_STEP_SUMMARY) {
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `\n### Public file sizes\n\n\`\`\`\n${formatReport(result)}\n\`\`\`\n`);
  }
  if (!result.ok) process.exit(1);
}
