# Frozen display and parser fixtures

Captured from reviewed production assets at commit `6adb42aa70d51ecc086f25e1f4f55030763697cd`, as of 2026-09-18. Deterministic gzip contains the original JSON bytes. These are test inputs, never production updates.

Specific-number display assertions and parser roundtrips read these fixtures, so tomorrow's date, prices or temporarily unavailable sources cannot invalidate yesterday's test cases. Live publication checks still validate current public assets against update-status and their fingerprints. Raw source bytes referenced by the cockpit remain in data/market/cockpit-v1/raw.

- `market-cockpit.json.gz`: source JSON SHA256 `61c3d1e46afa1bd0e0d63fbd4df046f1b16061d97071867c0e916952b2eaad70`
- `market-internals.json.gz`: source JSON SHA256 `60b2d43fc2c6845541fb96be30d30cb8ae6019c0d2ef29f5f2a57d5e130e1887`
- `industry-radar.json.gz`: source JSON SHA256 `f2c012f6aa0c3f603715117426366ade20270e82e3fe3742aa4c880cabd9591b`
