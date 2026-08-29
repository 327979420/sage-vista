import assert from "node:assert/strict";
import test from "node:test";

import {
  FRESHNESS_CRON,
  dispatchWorkflow,
  planForCron,
} from "../services/automation/eod_scheduler_worker.mjs";

const env = {
  GITHUB_OWNER: "owner",
  GITHUB_REPO: "repo",
  GITHUB_REF: "main",
  EOD_WORKFLOW: "daily-eod.yml",
  FRESHNESS_WORKFLOW: "eod-freshness-monitor.yml",
  GITHUB_ACTIONS_TOKEN: "test-token-must-not-leak",
};

test("EOD and freshness crons dispatch separate workflows", () => {
  assert.deepEqual(planForCron("47 23 * * 1-5", env), {
    workflow: "daily-eod.yml",
    inputs: { mode: "update", trigger_source: "cloudflare_cron" },
  });
  assert.deepEqual(planForCron(FRESHNESS_CRON, env), {
    workflow: "eod-freshness-monitor.yml",
    inputs: {},
  });
  assert.throws(() => planForCron("0 0 * * *", env), /Unregistered/);
});

test("dispatch uses the GitHub workflow endpoint without putting the token in the URL", async () => {
  let captured;
  const fakeFetch = async (url, options) => {
    captured = { url, options };
    return new Response(JSON.stringify({ workflow_run_id: 123 }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const result = await dispatchWorkflow(planForCron("17 0 * * 2-6", env), env, fakeFetch);
  assert.equal(result.dispatched, true);
  assert.equal(captured.url, "https://api.github.com/repos/owner/repo/actions/workflows/daily-eod.yml/dispatches");
  assert.equal(captured.url.includes(env.GITHUB_ACTIONS_TOKEN), false);
  assert.equal(captured.options.headers.Authorization, `Bearer ${env.GITHUB_ACTIONS_TOKEN}`);
  assert.deepEqual(JSON.parse(captured.options.body), {
    ref: "main",
    inputs: { mode: "update", trigger_source: "cloudflare_cron" },
  });
});

test("dispatch failures expose status and request id but never the token", async () => {
  const fakeFetch = async () => new Response("forbidden", {
    status: 403,
    headers: { "x-github-request-id": "safe-request-id" },
  });
  await assert.rejects(
    dispatchWorkflow(planForCron(FRESHNESS_CRON, env), env, fakeFetch),
    (error) => {
      assert.match(error.message, /HTTP 403/);
      assert.match(error.message, /safe-request-id/);
      assert.equal(error.message.includes(env.GITHUB_ACTIONS_TOKEN), false);
      return true;
    },
  );
});
