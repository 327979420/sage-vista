# Parked queue specs

Specs here are NOT picked up by `research/lab/run_queue.py` (it only reads `research/lab/queue/*.json`).

- `data-jp-universe-v1.json` (task 037) — parked 2026-10-19 by Claude: EODHD returned HTTP 404 for
  `exchange-symbol-list/TSE` in run 39215442000, which failed the whole research-lab job and skipped the daily
  forward record. Move it back only after the correct Japan exchange code is confirmed from EODHD's exchanges list.
  The pre-registration (docs/rules/08 #jp-exam, ledger §17) is unchanged; no Japan data was downloaded.
