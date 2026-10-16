# Task 006: read and write research datasets from a private repository

Read `tasks/README.md` first. Owner decision ADR-10 (2026-10-17): code stays public, the EODHD-derived datasets move to a private
repository. This card explicitly ALLOWS editing `research/lab/datasets.py` and `.github/workflows/research-lab.yml` (only these).

## Why
The 14 assets of the `research-datasets` release of the public repo are EODHD price data that anyone can download. Claude will copy
them to a private repo `327979420/sage-vista-data` (same release tag `research-datasets`, same asset names and SHA256). The code must
then read and write there, without exposing a token to other steps.

## Change
1. `research/lab/datasets.py`: every `gh release ...` call (in `upload` and `download`) adds `-R <repo>` when the environment variable
   `SV_DATA_REPO` is set, and runs with `GH_TOKEN` = `SV_DATA_TOKEN` (only in that subprocess's env) when `SV_DATA_TOKEN` is set.
   Without the variables, behaviour is exactly as today (local runs keep working). Keep the SHA256 verification as is.
   Put the repo/env handling in one small helper; no other behaviour change.
2. `.github/workflows/research-lab.yml`: at job level add `SV_DATA_REPO: 327979420/sage-vista-data` and
   `SV_DATA_TOKEN: ${{ secrets.DATA_REPO_TOKEN }}`. Nothing else in the workflow changes.
3. Tests in `tests/test_research_lab.py` or a new `tests/test_datasets_repo.py` (mock `subprocess.run`): with the variables unset the
   argv equals today's; with them set, argv contains `-R 327979420/sage-vista-data` and the env passed has GH_TOKEN = the data token
   while `os.environ` itself is unchanged; the frozen-code fingerprint test still passes.

## Not in scope
Do not touch `triangle15.py`, `triangle_forward.py`, `research/lab/forward/`, manifests, other workflows, or the release itself.
No network, no commits. Report the diff summary, tests run, Concerns (e.g. any other place that downloads release assets).

## After Codex (Claude + owner)
Claude creates the private repo and copies the assets with checksums; the owner creates a fine-grained token (contents read/write on
`sage-vista-data` only) and adds it as secret `DATA_REPO_TOKEN`; Claude merges, runs the lab once to verify, and only then (with the
owner's OK) removes the public copies.
