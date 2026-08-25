import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
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
