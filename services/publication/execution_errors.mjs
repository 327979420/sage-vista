// Fixed runtime classification; source HTTP classification remains in its source
// adapter. Unknown/storage failures are uncertain, never guessed into success.
export function classifyExecutionError(error) {
  const code = error?.message;
  if (code === 'execution_cancelled') return { action: 'yield', outcome: 'cancelled' };
  if (code === 'execution_job_budget_exhausted') return { action: 'yield', outcome: 'budget_exhausted' };
  if (code === 'execution_computation_timeout') return { action: 'retry', outcome: 'computation_timeout' };
  if (['execution_process_failed', 'execution_input_delivery_failed', 'execution_output_too_large'].includes(code)) return { action: 'block', outcome: 'computation_invalid' };
  if (['execution_validation_output_binding_invalid', 'execution_checkpoint_source_conflict', 'execution_dispatch_conflict'].includes(code)) return { action: 'block', outcome: 'contract_conflict' };
  // Lease/identity loss, missing originals, SQL failures and ambiguous completion
  // cannot safely update task state here. The next owned recovery reads facts.
  return { action: 'stop', outcome: 'recovery_required' };
}
