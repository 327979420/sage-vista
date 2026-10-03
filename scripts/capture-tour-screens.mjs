// Regenerate the first-visit tour screenshots from the real pages.
// Usage: start the site (npm run dev -- --port 5173), then
//   node scripts/capture-tour-screens.mjs [baseUrl]
// Needs Google Chrome; set CHROME to its path if it is not in the default place.
import {spawn} from 'node:child_process';
import {mkdirSync, mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';

const base = process.argv[2] ?? 'http://localhost:5173';
const chromePath = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const shots = [
 {image: 'multi-factor', url: '/', selector: '.candidateWorkspace', height: 620},
 {image: 'search', url: '/zh/watch/resonance/rare-opportunities?symbol=BJ', selector: '.candidateWorkspace', height: 680},
 {image: 'daily-setups', url: '/zh/watch/resonance/favorite-pattern', selector: '.shapeWorkspace', height: 620},
 {image: 'market', url: '/zh/watch/market', selector: '.cockpitGrid', height: 620},
];

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const chrome = spawn(chromePath, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--force-prefers-reduced-motion', '--remote-debugging-port=9340', `--user-data-dir=${mkdtempSync(path.join(tmpdir(), 'sv-tour-'))}`, 'about:blank'], {stdio: 'ignore'});
try {
 let targets;
 for (let i = 0; i < 50 && !targets; i++) { try { targets = await (await fetch('http://127.0.0.1:9340/json')).json(); } catch { await sleep(200); } }
 const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
 await new Promise(resolve => { ws.onopen = resolve; });
 let id = 0; const pending = new Map();
 ws.onmessage = event => { const message = JSON.parse(event.data); if (message.id && pending.has(message.id)) { pending.get(message.id)(message.result); pending.delete(message.id); } };
 const send = (method, params = {}) => new Promise(resolve => { const i = ++id; pending.set(i, resolve); ws.send(JSON.stringify({id: i, method, params})); });
 await send('Page.enable'); await send('Network.enable');
 await send('Emulation.setDeviceMetricsOverride', {width: 1240, height: 900, deviceScaleFactor: 1, mobile: false});
 for (const lang of ['en', 'zh']) {
  mkdirSync(`public/tour/${lang}`, {recursive: true});
  for (const cookie of [['sv-language-session', lang], ['sv-onboarded', '1']]) await send('Network.setCookie', {name: cookie[0], value: cookie[1], url: base});
  for (const shot of shots) {
   await send('Page.navigate', {url: base + shot.url}); await sleep(7000);
   const {result} = await send('Runtime.evaluate', {returnByValue: true, expression: `(() => { const r = document.querySelector(${JSON.stringify(shot.selector)}).getBoundingClientRect(); return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}; })()`});
   const box = result.value;
   const {data} = await send('Page.captureScreenshot', {format: 'webp', quality: 82, captureBeyondViewport: true, clip: {x: box.x, y: box.y, width: box.w, height: Math.min(box.h, shot.height), scale: 1}});
   writeFileSync(`public/tour/${lang}/${shot.image}.webp`, Buffer.from(data, 'base64'));
   console.log(`public/tour/${lang}/${shot.image}.webp`);
  }
 }
 ws.close();
} finally { chrome.kill(); }
