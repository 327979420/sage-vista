"""Synthetic metadata/date rollover of read-only tests; never rewrite public.

Only source reads are overlaid in memory. These are not reconstructed real market
sessions or a formal source bundle, and do not replace the real EOD integration.
"""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from services.contracts import adapt_legacy_file
from services.contracts.manifest import FROZEN_RELEASE_NAMES
from tests import test_m09_ledger, test_market_data_consumers, test_shared_contracts

ROOT = Path(__file__).resolve().parents[1]


class EodDateRolloverTests(unittest.TestCase):
    def test_daily_date_and_record_growth_do_not_invalidate_contract_regressions(self):
        public = ROOT / 'public'
        paths = [public / name for name in FROZEN_RELEASE_NAMES]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        current = date.fromisoformat(json.loads((public/'update-status.json').read_bytes())['source_latest_complete_date'])
        first = max(date(2026, 9, 4), current + timedelta(days=1))
        read_bytes, read_text = Path.read_bytes, Path.read_text
        daily = [p for p in paths if adapt_legacy_file(p).temporal_class == 'daily_snapshot']
        for offset in (0, 1):
            day = (first + timedelta(days=offset)).isoformat()
            overlay = {}
            for p in daily:
                value = json.loads(read_bytes(p))
                if 'as_of' in value:
                    value['as_of'] = day
                if p.name == 'update-status.json':
                    for key in value:
                        if key == 'source_latest_complete_date' or key.endswith('_as_of'):
                            value[key] = day
                if p.name.startswith('unified-v2-'):
                    value['coverage']['end'] = day
                if p.name in ('opportunity-ledger.json', 'signal-history.json'):
                    key, identity = ('events', 'event_id') if p.name.startswith('opportunity') else ('cases', 'signal_id')
                    added = dict(value[key][0])
                    added[identity] += ':synthetic-rollover-' + day
                    value[key].append(added)
                overlay[p] = json.dumps(value).encode()
            def bytes_at(path):
                return overlay[path] if path in overlay else read_bytes(path)
            def text_at(path, *args, **kwargs):
                return overlay[path].decode() if path in overlay else read_text(path, *args, **kwargs)
            with self.subTest(day=day), patch.object(Path, 'read_bytes', bytes_at), patch.object(Path, 'read_text', text_at):
                cases = [
                    test_m09_ledger.M09LedgerTests('test_current_legacy_samples_adapt_without_writing_or_formal_promotion'),
                    test_market_data_consumers.ForwardUniverseAndConsumerTests('test_2026_08_28_repository_sample_is_only_count_and_trigger_evidence'),
                    *[test_shared_contracts.SharedContractTests(name) for name in (
                        'test_current_files_adapt_without_modification',
                        'test_shadow_manifest_has_exact_hashes_and_roles',
                        'test_d1_research_summary_future_coverage_or_missing_source_fails',
                        'test_d1_daily_snapshot_wrong_date_or_future_evidence_fails')],
                ]
                for case in cases:
                    getattr(case, case._testMethodName)()
            self.assertEqual(before, {p: hashlib.sha256(read_bytes(p)).hexdigest() for p in paths})
