// Frozen real release shared by the website tests. Tests must never read the
// moving public/ output of the daily EOD job: new wording or values in live data
// must not block a release. Live English coverage is reported (warning only)
// by services/automation/report_untranslated.mjs in the EOD workflow.
import fs from 'node:fs';
import {gunzipSync} from 'node:zlib';
const root = new URL('../fixtures/public-2026-09-23/', import.meta.url);
export function fixture(name) {
 const plain = new URL(`${name}.json`, root);
 if (fs.existsSync(plain)) return JSON.parse(fs.readFileSync(plain, 'utf8'));
 return JSON.parse(gunzipSync(fs.readFileSync(new URL(`${name}.json.gz`, root))).toString('utf8'));
}
