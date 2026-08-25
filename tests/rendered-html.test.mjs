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
  assert.match(html, /<title>Sage Vista — Quantitative Equity Research<\/title>/i);
  assert.match(html, /SAGE VISTA/i);
  assert.match(html, /US Equity Signals/i);
  assert.doesNotMatch(html, /DISCORD_WEBHOOK_URL|EODHD_API_TOKEN/i);
});

test("server-renders the private research navigation", async () => {
  const html = await (await render()).text();
  assert.match(html, /指标共振/);
  assert.match(html, /PRIVATE RESEARCH/);
  assert.match(html, /QUANTITATIVE EQUITY RESEARCH/);
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
