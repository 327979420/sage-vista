import {appendFileSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export const ARTIFACT_NAME = 'site-preview-screenshots';
export const TOUR_SEEN_KEY = 'sv-onboarded';
export const PAGES = [
  {name: 'today', path: '/'},
  {name: 'portfolio', path: '/portfolio'},
  {name: 'signals', path: '/signals'},
  {name: 'forward', path: '/forward'},
    {name: 'patterns', path: '/patterns'},
  {name: 'reference', path: '/zh/watch/resonance/rare-opportunities'},
];
export const VIEWPORTS = [{width: 1440, height: 900}, {width: 390, height: 844}];

export function previewOrigin(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || !/^sv-preview\.[a-zA-Z0-9-]+\.workers\.dev$/.test(url.hostname) || url.port || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Expected the isolated sv-preview workers.dev origin');
  }
  return url.origin;
}
export function previewUrlFromLog(log) {
  const urls = [...new Set(log.match(/https:\/\/sv-preview\.[a-zA-Z0-9-]+\.workers\.dev\b/g) ?? [])];
  if (urls.length !== 1) throw new Error('Deploy log must identify exactly one sv-preview URL');
  return previewOrigin(urls[0]);
}

export async function captureScreenshots(baseUrl, output = ARTIFACT_NAME) {
  const origin = previewOrigin(baseUrl);
  mkdirSync(output, {recursive: true});
  const report = {previewUrl: origin, language: 'zh', capturedAt: new Date().toISOString(), results: []};
  let browser;
  try {
    const {chromium} = await import('playwright');
    browser = await chromium.launch();
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({viewport, deviceScaleFactor: 1, locale: 'zh-CN', reducedMotion: 'reduce'});
      try {
        await context.addCookies([{name: 'sv-language-session', value: 'zh', url: origin}]);
        await context.addInitScript(key => localStorage.setItem(key, '1'), TOUR_SEEN_KEY);
        for (const target of PAGES) {
          const page = await context.newPage();
          const filename = `${target.name}-${viewport.width}x${viewport.height}.png`;
          const result = {path: target.path, viewport, screenshot: filename, overflow: null, errors: []};
          report.results.push(result);
          page.on('pageerror', error => result.errors.push(error.message));
          try {
            const response = await page.goto(new URL(target.path, origin).href, {waitUntil: 'load', timeout: 60000});
            result.httpStatus = response?.status() ?? null;
            if (!response?.ok()) throw new Error(`Page HTTP status ${result.httpStatus}`);
            // Wait for hydration and data to reach either content or an explicit unavailable state.
            await page.waitForFunction(() => {
              const main = document.querySelector('main');
              return main && !/正在读取数据|正在读取已核新模型快照|行情状态载入中/.test(main.innerText);
            }, null, {timeout: 30000});
            await page.evaluate(() => document.fonts.ready);
            await page.locator('.svTourBackdrop').waitFor({state: 'hidden', timeout: 5000});
          } catch (error) {
            result.errors.push(error.message);
          }
          try {
            result.overflow = await page.evaluate(() => {
              const root = document.documentElement;
              const scrollWidth = Math.max(root.scrollWidth, document.body?.scrollWidth ?? 0);
              return {scrollWidth, clientWidth: root.clientWidth, horizontal: scrollWidth > root.clientWidth};
            });
            await page.screenshot({path: resolve(output, filename), fullPage: true, animations: 'disabled'});
          } catch (error) {
            result.errors.push(error.message);
            result.screenshot = null;
          } finally {
            await page.close();
          }
        }
      } finally {
        await context.close();
      }
    }
  } catch (error) {
    report.error = error.message;
  } finally {
    writeFileSync(resolve(output, 'overflow.json'), JSON.stringify(report, null, 2) + '\n');
    await browser?.close();
  }
  if (report.error || report.results.some(result => result.errors.length)) throw new Error(`Screenshot capture had errors; see ${output}/overflow.json`);
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  if (process.argv[2] === '--resolve-url') {
    const url = previewUrlFromLog(readFileSync(process.argv[3], 'utf8'));
    appendFileSync(process.env.GITHUB_OUTPUT, `url=${url}\n`);
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `Preview URL: ${url}\n\nScreenshot artifact: \`${ARTIFACT_NAME}\` (includes overflow.json)\n`);
  } else {
    await captureScreenshots(process.argv[2]);
  }
}
