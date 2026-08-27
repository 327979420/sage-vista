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
  assert.match(html, /Sage Vista UI v4\.1/);
  assert.match(html, /Build (?:local|[0-9a-f]{7})/);
  assert.doesNotMatch(html, /US Equity Signals|SIGNAL BOARD/i);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders the consolidated research navigation", async () => {
  const html = await (await render()).text();
  assert.match(html, /个股研究/);
  assert.match(html, /多因子机会/);
  assert.match(html, /行业与大盘/);
  assert.match(html, /历史与实验/);
});

test("server-renders the isolated Strategy Backtest research page", async () => {
  const response = await render("/zh/watch/resonance/strategy-backtest");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Strategy Backtest/);
  assert.match(html, /Tracker Backtest V1/);
  assert.match(html, /不进入生产排名/);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders Tracker Backtest V2 risk research", async () => {
  const response = await render("/zh/watch/resonance/strategy-backtest-v2");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Backtest V2/);
  assert.match(html, /Stop &amp; Risk-Reward/);
  assert.match(html, /不进入 production/);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders the point-in-time Market Regime research page", async () => {
  const response = await render("/zh/watch/resonance/market-regime");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Market Regime/);
  assert.match(html, /不参与 production/);
  assert.match(html, /验证市场环境能否改善冻结的 Long benchmark/);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders Factor Attribution research without production secrets", async () => {
  const response = await render("/zh/watch/resonance/factor-attribution");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Factor Attribution/);
  assert.match(html, /不改变 production 权重/);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders Ranking Research controls safely", async () => {
  const response = await render("/zh/watch/resonance/ranking-research");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Ranking Research/);
  assert.match(html, /同一 point-in-time 候选池/);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders Selection Research as an isolated experiment", async () => {
  const response = await render("/zh/watch/resonance/selection-research");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Stock Selection/);
  assert.match(html, /Leadership 与 Strong-Trend Pullback/);
  assert.match(html, /不改变 production/);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});
