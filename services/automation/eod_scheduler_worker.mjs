const EOD_CRONS = new Set([
  "47 23 * * 1-5",
  "17 0 * * 2-6",
  "47 0 * * 2-6",
  "17 1 * * 2-6",
  "47 1 * * 2-6",
  "17 2 * * 2-6",
  "17 3 * * 2-6",
]);

export const FRESHNESS_CRON = "37 4 * * 2-6";

function required(env, name) {
  const value = env[name];
  if (!value) throw new Error(`Missing required scheduler binding: ${name}`);
  return value;
}

export function planForCron(cron, env) {
  if (EOD_CRONS.has(cron)) {
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
    const plan = planForCron(controller.cron, env);
    ctx.waitUntil(dispatchWorkflow(plan, env));
  },
};
