# Task 017: deploy the app data when it changes

Read `tasks/README.md` first. Found 2026-10-17 after the first live run: `research.lab.app_data --publish` commits `public/app/*.json`
with `[skip ci]`, and `deploy-site.yml` only triggers on app/code paths, so the new files reach the live site only with the next EOD
release (after a Friday close that means Tuesday). The owner's main use is "open 今日 at the weekend" (PRD US-1), so the data must ship
the same day.

## Change
- `research.lab.app_data.publish()` returns whether it pushed a new commit (it already returns early when the tree is unchanged).
- `research-lab.yml`: when it pushed, dispatch `deploy-site.yml` on main (`gh workflow run deploy-site.yml --ref main` with
  `GH_TOKEN: ${{ github.token }}`; add `actions: write` to the job permissions). Dispatch is allowed with GITHUB_TOKEN. Pass the
  "pushed" result between steps through `$GITHUB_OUTPUT`.
- Respect the 23:30-04:30 UTC window: never dispatch inside it (the deploy shares the `sage-vista-production-deploy` concurrency
  group with the EOD job, so it queues behind a running EOD release rather than racing it - keep it that way).
- No change to deploy-site.yml triggers, to the EOD job, or to any page.

## Tests
Python: `publish()` returns False when the tree is unchanged and True after a push (mock git as the existing tests do). A YAML check that
the dispatch step only runs when the output is "true" and that the job has `actions: write`.

## Deliverables
Code + tests on the branch, codex report with Concerns. No network, no commits.
