import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, rmSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync, gunzipSync } from 'node:zlib';

export const policy = JSON.parse(readFileSync(new URL('./public-archive-policy.json', import.meta.url), 'utf8'));
const storedCompressed = new Set(policy.storedCompressed ?? []);

// GitHub rejects files above 100 MiB, so Git keeps these archives as <name>.gz.
// Returns the file that holds `name` in `folder`, and whether it is gzip.
export function archiveSource(folder, name) {
  const plain = path.join(folder, name);
  if (!storedCompressed.has(name)) return { file: plain, compressed: false };
  const stored = `${plain}.gz`;
  if (existsSync(stored) && existsSync(plain)) throw new Error(`Both ${plain} and ${stored} exist; keep only ${name}.gz`);
  return existsSync(stored) ? { file: stored, compressed: true } : { file: plain, compressed: false };
}

// The exact JSON bytes of an archive, whichever form holds it.
export function readArchive(folder, name) {
  const { file, compressed } = archiveSource(folder, name);
  const raw = readFileSync(file);
  return compressed ? gunzipSync(raw) : raw;
}

// Only the generated deployment directory changes. Research keeps its original JSON.
export function packageArchives(source = 'public', destination = 'dist/client', limit = policy.maxAssetBytes) {
  const packaged = policy.archives.map(name => {
    const original = readArchive(source, name);
    const deployed = archiveSource(destination, name).file;
    // Require a fresh build so a stale source cannot accidentally be published.
    if (!readArchive(destination, name).equals(original)) throw new Error(`Build/source mismatch: ${name}`);
    const gzip = gzipSync(original, { level: 9 });
    if (gzip.length > limit) throw new Error(`Hosting limit exceeded: ${name}`);
    if (!gunzipSync(gzip).equals(original)) throw new Error(`Archive verification failed: ${name}`);
    return { name, original, gzip, deployed };
  });
  const archiveDirectory = path.join(destination, policy.assetPrefix);
  mkdirSync(archiveDirectory, { recursive: true });
  // Validate and write every replacement before removing any generated raw file.
  for (const item of packaged) writeFileSync(path.join(archiveDirectory, `${item.name}.gz`), item.gzip);
  for (const item of packaged) rmSync(item.deployed);
  function checkDirectory(folder) {
    for (const name of readdirSync(folder)) {
      const file = path.join(folder, name), info = statSync(file);
      if (info.isDirectory()) checkDirectory(file);
      else if (info.size > limit) throw new Error(`Hosting limit exceeded: ${file}`);
    }
  }
  checkDirectory(destination);
  return packaged.map(({ name, original, gzip }) => ({ name, originalBytes: original.length, deployedBytes: gzip.length }));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log(JSON.stringify(packageArchives(), null, 2));
}
