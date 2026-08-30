import assert from "node:assert/strict";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, {
      headers: { accept: "text/html" },
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
  assert.match(html, /<title>Sage Vista — 今日研究总览<\/title>/i);
  assert.match(html, /SAGE VISTA/i);
  assert.match(html, /今日研究总览/i);
  assert.match(html, /Sage Vista UI v6\.1/);
  assert.match(html, /Build (?:local|[0-9a-f]{7})/);
  assert.doesNotMatch(html, /US Equity Signals|SIGNAL BOARD/i);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders the four-product navigation", async () => {
  const html = await (await render("/")).text();
  assert.doesNotMatch(html, /个股研究/);
  assert.match(html, /多因子机会/);
  assert.match(html, /我最喜欢形态/);
  assert.match(html, /行业与大盘/);
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
    ["/zh/watch/market", "/zh/watch/industry-radar"],
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
  assert.match(html, /只看你最关心的四件事/);
  assert.match(html, /生产权重 0/);
  assert.match(html, /发生回调/);
  assert.match(html, /形成双底/);
  assert.match(html, /三推突破/);
  assert.match(html, /踩到位置/);
  assert.match(html, /4\/4不是胜率/);
});

test("experiment pages are retired from the website", async () => {
  const routes = [
    "/zh/watch/resonance/research",
    "/zh/watch/resonance/strategy-backtest",
    "/zh/watch/resonance/strategy-backtest-v2",
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
