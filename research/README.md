# Northstar research ledger

Every factor or model experiment must be recorded before its result is used. The ledger preserves the specification, data window, research version and status, including failed experiments. A favourable result is not a trading recommendation.

Promotion sequence: `idea → challenger → walk-forward validated → paper champion → retired`.

The local SQLite research database is reproducible from `services/scanner/research_pipeline.py` and is intentionally excluded from source control. Versioned aggregate evidence is published in `public/research-report.json`.

## Minimum acceptable market-data contract

Before a strategy can become a paper champion, its test data must include adjusted daily OHLCV, historical listings and delistings, point-in-time fundamentals keyed to public availability dates, historical classifications, and auditable corporate actions. Missing values stay missing; no future value may be silently carried backward. Every source and transformation receives a version.

Individual factors are tested first. Combination testing starts only after validation-period stability and redundancy analysis: highly correlated indicators count as one family, not multiple confirmations.
