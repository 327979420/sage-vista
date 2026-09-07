# Sage Vista execution entry

Follow the user's current instructions and existing authorization. The single execution policy is [docs/rules/01_GOVERNANCE.md](docs/rules/01_GOVERNANCE.md); read it once per task. Do not load every module for a single-module change.

## Minimum reading

- Check Git status in the actual working directory and read `docs/CURRENT_STATUS_ZH.md`; verify only the machine sources relevant to the task. Local, other worktrees and production may differ. Protect other tasks' changes.
- Use `docs/rules/README.md` to choose the one affected business rule (for example `docs/rules/04_SCORING.md` for scoring). Use `docs/CODEBASE_MAP_ZH.md` only to locate the implementation.
- Read only the relevant entry in `docs/CHANGE_REQUESTS_ZH.md`. Continue already authorized work without another approval round.
- `README.md` is the human entry. `docs/SAGE_VISTA_RULEBOOK_ZH.md` is optional product context; `docs/NEXT_SESSION_HANDOFF_ZH.md` is a compatibility pointer, not another required checklist.
- Historical designs, decision logs and acceptance reports are reference evidence, not mandatory onboarding. Consult the exact record only when it is needed to resolve the current task.

All execution, authorization, validation and documentation rules are maintained in the linked governance file. Do not duplicate them here.
