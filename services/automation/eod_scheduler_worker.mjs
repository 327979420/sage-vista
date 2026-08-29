export const EOD_WINDOW_CRON = "17,47 0-3,23 * * 1-6";
export const FRESHNESS_CRON = "37 4 * * 2-6";

const NEXT_DAY_EOD_TIMES = new Set([
  "00:17",
  "00:47",
  "01:17",
  "01:47",
  "02:17",
  "03:17",
]);

function required(env, name) {
  const value = env[name];
  if (!value) throw new Error(`Missing required scheduler binding: ${name}`);
  return value;
}

export function isEodDispatchTime(scheduledTime) {
  if (!Number.isFinite(scheduledTime)) {
    throw new Error("Missing valid scheduledTime for EOD window");
  }
  const date = new Date(scheduledTime);
  const weekday = date.getUTCDay();
  const time = `${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}`;
  if (weekday >= 1 && weekday <= 5 && time === "23:47") return true;
  return weekday >= 2 && weekday <= 6 && NEXT_DAY_EOD_TIMES.has(time);
}

export function planForCron(cron, env, scheduledTime) {
  if (cron === EOD_WINDOW_CRON) {
    if (!isEodDispatchTime(scheduledTime)) return null;
    return {
      workflow: required(env, "EOD_WORKFLOW"),
      inputs: { mode: "update", trigger_source: "cloudflare_cron" },
    };
  }
  if (cron === FRESHNESS_CRON) {
    return { workflow: required(env, "FRESHNESS_WORKFLOW"), inputs: {} };
  }
  throw new Error(`Unregistered scheduler cron: ${cron}`);
}

export async function dispatchWorkflow(plan, env, fetchImpl = fetch) {
  const owner = required(env, "GITHUB_OWNER");
  const repo = required(env, "GITHUB_REPO");
  const ref = required(env, "GITHUB_REF");
  const token = required(env, "GITHUB_ACTIONS_TOKEN");
  const workflow = encodeURIComponent(plan.workflow);
  const response = await fetchImpl(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": "SageVistaEodScheduler/1.0",
        "X-GitHub-Api-Version": "2026-03-10",
      },
      body: JSON.stringify({ ref, inputs: plan.inputs }),
    },
  );
  if (!response.ok) {
    const requestId = response.headers.get("x-github-request-id");
    const suffix = requestId ? ` (request ${requestId})` : "";
    throw new Error(`GitHub workflow dispatch failed with HTTP ${response.status}${suffix}`);
  }
  return {
    dispatched: true,
    workflow: plan.workflow,
    status: response.status,
  };
}

export default {
  async scheduled(controller, env, ctx) {
    const plan = planForCron(controller.cron, env, controller.scheduledTime);
    if (!plan) return;
    ctx.waitUntil(dispatchWorkflow(plan, env));
  },
};
