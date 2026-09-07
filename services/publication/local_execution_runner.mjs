// Local protected-runtime composition. No RPC, source fetch, or deployment route.
// pythonExecutable is installed by the trusted host, never supplied on task wire.
import { classifyExecutionError } from './execution_errors.mjs';
import { spawn } from 'node:child_process';
import { isAbsolute, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ExecutionComputationSession } from './execution_session.mjs';
import { ExecutionScheduler } from './execution_scheduler.mjs';
import { ExecutionTaskArchive } from './execution_archive.mjs';
const WORKER = fileURLToPath(new URL('./preparation_validation_worker.py', import.meta.url));
const ROOT = dirname(dirname(dirname(WORKER)));

// Calls the existing isolated worker with its pre/post full-source guard.
// Both output pipes are handled without blocking lease checks; abort kills and
// waits for close before rejecting. No caller command, arguments, or retries.
function compute(python, raw, deadline, signal, check) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new Error('execution_cancelled')); return; }
    const remaining = Math.min(30000, deadline - Date.now());
    if (remaining <= 0) { reject(new Error('execution_job_budget_exhausted')); return; }
    let failure = null, total = 0, chunks = [], previous = Date.now();
    const child = spawn(python, ['-I', WORKER], { cwd: ROOT, env: {}, stdio: ['pipe', 'pipe', 'ignore'] });
    const stop = reason => { failure ??= reason; child.kill('SIGKILL'); };
    const aborted = () => stop('execution_cancelled');
    const timeout = setTimeout(() => stop(remaining < 30000 ? 'execution_job_budget_exhausted' : 'execution_computation_timeout'), remaining);
    const monitor = setInterval(() => {
      try {
        const now = Date.now();
        if (now < previous) { stop('execution_clock_invalid'); return; }
        if (now >= deadline) { stop('execution_job_budget_exhausted'); return; }
        previous = now; check();
      } catch { stop('execution_lease_lost'); }
    }, 1000);
    signal?.addEventListener('abort', aborted, { once: true });
    if (signal?.aborted) aborted();
    child.on('error', () => { failure ??= 'execution_process_failed'; });
    child.stdin.on('error', () => stop('execution_input_delivery_failed'));
    child.stdout.on('data', chunk => {
      total += chunk.length;
      if (total > 2 * 1024 * 1024) { chunks = []; stop('execution_output_too_large'); }
      else if (!failure) chunks.push(chunk);
    });
    child.on('close', code => {
      clearTimeout(timeout); clearInterval(monitor); signal?.removeEventListener('abort', aborted);
      try {
        if (failure || code !== 0 || total === 0) throw new Error(failure ?? 'execution_process_failed');
        if (Date.now() < previous || Date.now() >= deadline) throw new Error('execution_job_budget_exhausted');
        check(); resolve(new Uint8Array(Buffer.concat(chunks)));
      } catch (error) { reject(error); }
    });
    child.stdin.end(raw);
  });
}

export class LocalExecutionRunner {
  #storage; #bucket; #python; #session; #tasks;
  constructor(storage, bucket, { pythonExecutable } = {}) {
    if (typeof pythonExecutable !== 'string' || !isAbsolute(pythonExecutable)) throw new Error('execution_installed_python_required');
    this.#storage = storage; this.#bucket = bucket; this.#python = pythonExecutable;
    this.#session = new ExecutionComputationSession(storage, bucket);
    this.#tasks = new ExecutionTaskArchive(storage, bucket);
  }
  async runTask(identity, token, taskId, requestBytes, { signal } = {}) {
    identity = structuredClone(identity); token = structuredClone(token);
    if (!(requestBytes instanceof Uint8Array)) throw new Error('execution_request_bytes_required');
    const request = new Uint8Array(requestBytes);
    let dispatched;
    const scheduler = new ExecutionScheduler(this.#storage, this.#bucket, {
      readiness: async (initial, budget) => {
        if (Date.now() >= budget.deadline_ms) throw new Error('execution_job_budget_exhausted');
        if (signal?.aborted) throw new Error('execution_cancelled');
        const prepared = await this.#session.prepare(identity, token, taskId, request);
        const check = () => this.#tasks.withCurrentTask(identity, token, taskId, initial.current, () => {},
          { resolveDeadlineMs: () => budget.deadline_ms });
        check();
        const output = await compute(this.#python, prepared.input_bytes, budget.deadline_ms, signal, check);
        const proof = await this.#session.inspect(identity, token, prepared.input.sha256, output);
        dispatched = { prepared, output };
        // Fixed next-pair evidence only. No guessed calendar or caller EOD flag.
        return { mature: proof.has_next_pair, eod_ms: null };
      },
    });
    let checkpoint = null;
    try {
    for (;;) {
      if (signal?.aborted) throw new Error('execution_cancelled');
      const pending = scheduler.list().find(item => item.snapshot.root.task_id === taskId)?.schedule;
      if (pending?.state.state === 'running' && pending.dispatch_input_sha) {
        const bounded = { ...identity, expires_at: Math.min(identity.expires_at, pending.original_expires_at,
          Math.floor((pending.job_started_ms + 600000) / 1000)) };
        const saved = await this.#session.readPrepared(bounded, token, pending.dispatch_input_sha);
        if (!saved.completed) {
          const check = () => this.#tasks.withCurrentTask(bounded, token, taskId, saved.source_snapshot, () => {});
          const output = await compute(this.#python, saved.input_bytes, bounded.expires_at * 1000, signal, check);
          await this.#session.accept(bounded, token, pending.dispatch_input_sha, output,
            { verifyCommit: () => scheduler.assertRunning(taskId, pending.position, identity, token) });
        }
        checkpoint = await scheduler.checkpoint(bounded, token, taskId, pending.position, pending.dispatch_input_sha);
        if (checkpoint.state.state !== 'running') return { status: 'caught_up_for_input', checkpoint };
        continue;
      }
      const claimed = await scheduler.claim(identity, token, taskId);
      if (!claimed.claimed) {
        if (claimed.reason === 'job_budget_exhausted') throw new Error('execution_job_budget_exhausted');
        return { status: claimed.reason, checkpoint };
      }
      let attempt = claimed.attempt;
      const bounded = { ...identity, expires_at: Math.min(identity.expires_at, attempt.original_expires_at,
        Math.floor((attempt.job_started_ms + 600000) / 1000)) };
      if (signal?.aborted) throw new Error('execution_cancelled');
      attempt = await scheduler.bindDispatch(bounded, token, taskId, attempt.position, dispatched.prepared.input.sha256, dispatched.output);
      await this.#session.accept(bounded, token, dispatched.prepared.input.sha256, dispatched.output,
        { verifyCommit: () => scheduler.assertRunning(taskId, attempt.position, identity, token) });
      checkpoint = await scheduler.checkpoint(bounded, token, taskId, attempt.position, dispatched.prepared.input.sha256);
      if (checkpoint.state.state !== 'running') return { status: 'caught_up_for_input', checkpoint };
    }
    } catch (error) {
      const classified = classifyExecutionError(error);
      if (classified.action === 'stop') throw error;
      const stopped = await scheduler.settle(identity, token, taskId, classified.outcome);
      return { status: stopped?.state.state ?? 'queued', outcome: classified.outcome, checkpoint: stopped };
    }
  }
}
