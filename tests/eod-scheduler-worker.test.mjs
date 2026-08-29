import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  EOD_WINDOW_CRON,
  FRESHNESS_CRON,
  dispatchWorkflow,
  isEodDispatchTime,
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

const monday2347 = Date.UTC(2026, 7, 31, 23, 47);
const tuesday0017 = Date.UTC(2026, 8, 1, 0, 17);

test("two Cloudflare crons stay within the free-plan trigger limit", () => {
  const config = JSON.parse(readFileSync(new URL("../wrangler.eod-scheduler.jsonc", import.meta.url), "utf8"));
  assert.deepEqual(config.triggers.crons, [EOD_WINDOW_CRON, FRESHNESS_CRON]);
  assert.equal(config.triggers.crons.length, 2);
});

test("the consolidated EOD window preserves only the seven exact dispatch times", () => {
  const allowed = [
    monday2347,
    tuesday0017,
    Date.UTC(2026, 8, 1, 0, 47),
    Date.UTC(2026, 8, 1, 1, 17),
    Date.UTC(2026, 8, 1, 1, 47),
    Date.UTC(2026, 8, 1, 2, 17),
    Date.UTC(2026, 8, 1, 3, 17),
  ];
  for (const scheduledTime of allowed) assert.equal(isEodDispatchTime(scheduledTime), true);

  const ignored = [
    Date.UTC(2026, 7, 31, 0, 17),
    Date.UTC(2026, 7, 31, 23, 17),
    Date.UTC(2026, 8, 1, 2, 47),
    Date.UTC(2026, 8, 1, 3, 47),
    Date.UTC(2026, 8, 5, 23, 47),
  ];
  for (const scheduledTime of ignored) assert.equal(isEodDispatchTime(scheduledTime), false);
});

test("EOD and freshness crons dispatch separate workflows", () => {
  assert.deepEqual(planForCron(EOD_WINDOW_CRON, env, monday2347), {
    workflow: "daily-eod.yml",
    inputs: { mode: "update", trigger_source: "cloudflare_cron" },
  });
  assert.equal(planForCron(EOD_WINDOW_CRON, env, Date.UTC(2026, 7, 31, 23, 17)), null);
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
  const result = await dispatchWorkflow(planForCron(EOD_WINDOW_CRON, env, tuesday0017), env, fakeFetch);
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
