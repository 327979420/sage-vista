import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

// Construct an allowlisted config; never spread production deployment settings.
export function previewConfig(build, ref, runId) {
  if (!ref?.startsWith('refs/heads/') || ref === 'refs/heads/main') throw new Error('Preview requires a non-main branch');
  if (!/^\d+$/.test(runId ?? '')) throw new Error('Invalid run ID');
  if (!build.main || !build.assets?.directory || !build.compatibility_date) throw new Error('Incomplete build config');
  return {
    name: 'sv-preview',
    main: build.main,
    compatibility_date: build.compatibility_date,
    compatibility_flags: build.compatibility_flags ?? [],
    no_bundle: true,
    rules: [{ type: 'ESModule', globs: ['**/*.js', '**/*.mjs'] }],
    assets: { directory: build.assets.directory, binding: 'ASSETS' },
    workers_dev: true,
    routes: [],
    preview_urls: false,
  };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const config = previewConfig(JSON.parse(readFileSync('dist/server/wrangler.json', 'utf8')), process.env.GITHUB_REF, process.env.GITHUB_RUN_ID);
  writeFileSync('dist/server/wrangler.preview.json', JSON.stringify(config, null, 2) + '\n');
}
