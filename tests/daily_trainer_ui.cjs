// Local-only browser checks. Set NODE_PATH to an installed Playwright package directory.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'work/site-v2/daily-trainer-1.html'),'utf8');
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://daily.test/**',r=>r.fulfill({contentType:'text/html',body:html}));
 await page.goto('http://daily.test/');
 assert.match(await page.locator('#status').innerText(),/刷新会丢失/);
 assert.equal(await page.locator('#cells button').count(),100);
 assert.equal(await page.locator('#chart svg').count(),1);
 const symbol=await page.evaluate(()=>BANK.cases[0].result.symbol);
 assert(!((await page.locator('main').innerText()).includes(symbol)));
 await page.locator('#note').fill('<img src=x onerror=alert(1)>');
 await page.keyboard.press('d');assert.equal(await page.locator('#count').innerText(),'0 / 100');
 await page.locator('[data-c="3"]').click();await page.locator('#wrong').check();await page.locator('#do').click();
 assert.equal(await page.locator('#title').innerText(),'第 2 题');
 for(let i=1;i<10;i++)await page.keyboard.press(i%2?'n':'d');
 assert.equal(await page.locator('#count').innerText(),'10 / 100');
 assert.equal(await page.locator('dialog').evaluate(e=>e.open),true);
 assert((await page.locator('#summaryContent').innerText()).includes(symbol));
 assert.equal(await page.locator('#summaryContent img').count(),0);
 await page.keyboard.press('d');assert.equal(await page.locator('#count').innerText(),'10 / 100');
 await page.locator('#continue').click();assert.equal(await page.locator('#title').innerText(),'第 11 题');
 await page.locator('[data-i="0"]').click();assert(await page.locator('#do').isDisabled());
 assert.equal(await page.locator('#wrong').isChecked(),true);
 await page.screenshot({path:path.join(root,'work/v3w/daily1-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(root,'work/v3w/daily1-mobile.png'),fullPage:true});
 await page.reload();assert.equal(await page.locator('#count').innerText(),'0 / 100');
 // Mock only: actual Claude DB persists and publishes in Claude's acceptance step.
 await page.addInitScript(()=>{
  window.mockSaved={};window.mockFail=true;
  window.claude={use:async()=>({collection:name=>{
   if(name!=='daily1')throw Error('collection');
   return {
    onSnapshot:cb=>{window.mockSnapshot=cb;cb({docs:[]})},
    doc:id=>({acquire:async()=>{if(window.mockFail)throw Error('offline');return {acquired:true}},get:async()=>({exists:id in window.mockSaved,data:()=>window.mockSaved[id]}),set:async a=>{
     if(window.mockFail)throw Error('offline');
     window.mockSaved[id]=a;
     window.mockSnapshot({docs:Object.entries(window.mockSaved).map(([id,a])=>({id,data:()=>a}))});
    }})
   };
  }})};
 });
 await page.reload();await page.locator('#do').click();assert.match(await page.locator('#status').innerText(),/保存失败/);
 await page.evaluate(()=>window.mockFail=false);await page.locator('#retry').click();assert.match(await page.locator('#status').innerText(),/已保存/);
 const saved=await page.evaluate(()=>window.mockSaved);assert.equal(Object.keys(saved).length,1);
 await page.locator('#note').fill('下一题草稿');await page.locator('[data-c="2"]').click();
 await page.evaluate(()=>window.mockSnapshot({docs:Object.entries(window.mockSaved).map(([id,a])=>({id,data:()=>a}))}));
 assert.equal(await page.locator('#note').inputValue(),'下一题草稿');assert.equal(await page.locator('[data-c="2"]').getAttribute('aria-pressed'),'true');
 const restored=await browser.newPage();await restored.route('http://daily.test/**',r=>r.fulfill({contentType:'text/html',body:html}));
 await restored.addInitScript(saved=>{window.claude={use:async()=>({collection:()=>({onSnapshot:cb=>cb({docs:Object.entries(saved).map(([id,a])=>({id,data:()=>a}))})})})}},saved);
 await restored.goto('http://daily.test/');assert.equal(await restored.locator('#count').innerText(),'1 / 100');assert.equal(await restored.locator('#title').innerText(),'第 2 题');
 assert.deepEqual(errors,[]);console.log('daily trainer UI: memory warning, D/N, auto advance, locked answers, batch reveal, escaping, responsive layout, mock DB retry and restore passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
