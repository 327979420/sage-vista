# Northstar research ledger

Every factor or model experiment must be recorded before its result is used. The ledger preserves the specification, data window, research version and status, including failed experiments. A favourable result is not a trading recommendation.

Promotion sequence: `idea → challenger → walk-forward validated → paper champion → retired`.

The local SQLite research database is reproducible from `services/scanner/research_pipeline.py` and is intentionally excluded from source control. Versioned aggregate evidence is published in `public/research-report.json`.
