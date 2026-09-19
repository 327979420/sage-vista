"""Executed in the original account's Git checkout, never under today's policy."""
import json
import sys
from pathlib import Path
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.cr056_runner import run_snapshot
from services.scanner.support_risk import signal_support_plan
from services.contracts.cr056_policy import POLICY_FINGERPRINT, POLICY_VERSION
from research.backtest.run_store import encode, sha256

cache, output = map(Path, sys.argv[1:3])
raw = {s: json.loads((cache / (s + '.json')).read_bytes()) for s in ('ELV', 'SPY')}
sessions = [r['date'] for r in raw['SPY'] if '2026-02-02' <= r['date'] <= '2026-02-27']
stage = output / 'stage'; stage.mkdir(parents=True, exist_ok=True)
results = []
for day in sessions:
    sources = []
    for symbol, values in raw.items():
        content = encode([r for r in values if r['date'] <= day])
        (stage / (symbol + '.json')).write_bytes(content)
        sources.append({'symbol': symbol, 'repaired_sha256': sha256(content), 'source_sha256': sha256(content)})
    report = run_snapshot(stage, as_of=day, history={'days': []}, code_commit='8532d13a8bf7bcb0fc9a6b7bd60b3ccacce0c160',
                          input_report={'as_of': day, 'result_role': 'legacy_comparison_input_repair', 'repaired': sources, 'repaired_count': 2, 'excluded_count': 0, 'excluded': {}})
    item = next(r for r in report['reviews'] if r['symbol'] == 'ELV')
    item.pop('rank', None)  # The two-stock probe cannot establish a universe rank.
    rows = normalized_comparison_rows([r for r in raw['ELV'] if r['date'] <= day], as_of=day)
    item['support_plan'] = signal_support_plan(rows)
    results.append(item)
(output / 'legacy-elv-probe.json').write_bytes(encode({'policy': POLICY_VERSION, 'fingerprint': POLICY_FINGERPRINT, 'days': results}))
