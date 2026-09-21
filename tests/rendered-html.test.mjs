import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/", cookie = "") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html", cookie },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Sage Vista application", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Sage Vista — 大盘<\/title>/i);
  assert.match(html, /SAGE VISTA/i);
  assert.match(html, /<html lang="zh-CN">/);
  assert.match(html, /大盘/i);
  assert.match(html, /Sage Vista UI v6\.1/);
  assert.match(html, /Build (?:local|[0-9a-f]{7})/);
  const expectedCommit = process.env.SAGE_DEPLOYMENT_COMMIT ?? process.env.GITHUB_SHA ?? "local";
  const buildMarker = html.match(/<span>(Build [^<]+)<\/span>/)?.[1];
  assert.equal(buildMarker, `Build ${expectedCommit.slice(0, 7)}`);
  assert.doesNotMatch(html, /US Equity Signals|SIGNAL BOARD/i);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders the four-product navigation", async () => {
  const html = await (await render("/")).text();
  assert.doesNotMatch(html, /个股研究/);
  assert.match(html, /多因子机会/);
  assert.match(html, /我最喜欢形态/);
  assert.match(html, /行业/);
  assert.doesNotMatch(html, /历史与实验/);
  assert.match(html, /href="\/zh\/watch\/resonance\/rare-opportunities"/);
  assert.match(html, /href="\/zh\/watch\/industry-radar"/);
});

test("the retired MACD Tracker product page is gone", async () => {
  const response = await render("/zh/watch/resonance/macd");
  assert.equal(response.status, 404);
});

test("retired product routes redirect to maintained modules", async () => {
  const routes = [
    ["/technical", "/zh/watch/resonance/rare-opportunities"],
    ["/data-quality", "/"],
    ["/zh", "/"],
    ["/zh/watch/resonance", "/zh/watch/market"],
    ["/zh/watch/resonance/rsi", "/zh/watch/resonance/rare-opportunities"],
  ];

  for (const [path, expected] of routes) {
    const response = await render(path);
    assert.ok([307, 308].includes(response.status), `${path} returned ${response.status}`);
    assert.equal(new URL(response.headers.get("location"), "http://localhost").pathname + new URL(response.headers.get("location"), "http://localhost").search, expected);
  }
});

test("server-renders the independent favorite-pattern tracker", async () => {
  const response = await render("/zh/watch/resonance/favorite-pattern");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /我最喜欢形态/);
  assert.match(html, /热门股 · 日线 · 形态/);
  assert.match(html, /先确认底部/);
  assert.match(html, /正在读取日线形态/);
  assert.doesNotMatch(html, /4\/4|生产权重 0/);
});

test("experiment pages are retired from the website", async () => {
  const routes = [
    "/zh/watch/resonance/research",
    "/zh/watch/resonance/strategy-backtest",
    "/zh/watch/resonance/market-regime",
    "/zh/watch/resonance/factor-attribution",
    "/zh/watch/resonance/ranking-research",
    "/zh/watch/resonance/selection-research",
  ];
  for (const path of routes) {
    const response = await render(path);
    assert.ok([307, 308].includes(response.status), `${path} returned ${response.status}`);
    assert.equal(new URL(response.headers.get("location"), "http://localhost").pathname, "/");
  }
});

test("multi-factor route renders the candidate snapshot boundary without duplicate legacy controls", async () => {
  const response = await render("/zh/watch/resonance/rare-opportunities");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /正在读取已核新模型快照/);
  assert.doesNotMatch(html, /旧版本排行与因子研究留档/);
  assert.doesNotMatch(html, /共同门票.*个样本/);
});


test("renders research history with pending account entry and retained comparison", async()=>{
  const response=await render("/zh/backtest");
  assert.equal(response.status,200);
  const html=await response.text();
  assert.match(html,/class="active" aria-current="page" href="\/zh\/backtest"/);assert.match(html,/正在读取研究配置/);assert.match(html,/早期20笔成交工程对账/);
});

test("old research bookmark redirects to independent backtest page", async()=>{
 const response=await render("/zh/watch/resonance/strategy-backtest-v2");
 assert.equal(response.status,307); assert.equal(response.headers.get("location"),"/zh/backtest");
});


test("Market is a real product page and the retired overview is absent", async () => {
 const response=await render("/zh/watch/market");
 assert.equal(response.status,200);
 const html=await response.text();
 assert.match(html,/先看结论，再看证据/);
 assert.match(html,/正在读取今日快照/);
 assert.match(html,/href="\/zh\/watch\/market"/);
 assert.doesNotMatch(html,/今日研究总览|精选机会，不追高/);
});

test("industry owns its title and excludes the market hero", async()=>{
 const html=await (await render('/zh/watch/industry-radar')).text();
 assert.match(html,/<title>Sage Vista — 行业<\/title>/);
 assert.match(html,/每日行业速览/);
 assert.doesNotMatch(html,/大盘环境 ·|行业与大盘/);
});


test("language cookie controls first render and never leaks between requests", async()=>{
 const pages=[['/','Market'],['/zh/watch/market','Market'],['/zh/watch/industry-radar','Industries'],['/zh/watch/resonance/rare-opportunities','Candidates'],['/zh/watch/resonance/favorite-pattern','Daily Patterns'],['/zh/backtest','Backtests']];
 for(const[path,title]of pages){
  const response=await render(path,'sv-language=en');assert.equal(response.status,200);
  const html=await response.text();assert.match(html,/<html lang="en">/);assert.ok(html.includes(title));assert.match(html,/lang="en" aria-pressed="true"/);
  assert.doesNotMatch(html.split('</head>')[1].split('<script')[0].replace(/>中文</g,'>Chinese<'),/[\u3400-\u9fff]/);
 }
 const zh=await (await render('/','sv-language=zh')).text();assert.match(zh,/<html lang="zh-CN">/);assert.match(zh,/正在读取今日快照/);
 const invalid=await (await render('/','sv-language=invalid')).text();assert.match(invalid,/<html lang="zh-CN">/);
});
