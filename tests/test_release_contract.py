"""Release contract gates real corruption; bad-day content is only a warning.

Also proves the unit suite no longer depends on the day's generated public/
assets: it re-runs every formerly data-dependent test module while reads of
ROOT/public are served from realistic bad-day bundles.
"""
import gzip
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from services.scanner.market_external import run as build_external
from services.scanner.release_contract import check_release
from tests.public_fixture import PUBLIC_FIXTURE, PUBLIC_FIXTURE_DAY as DAY, ROOT, changed, reseal

# test_cr056_daily lost its only public/ read (now a release-contract check)
# and takes ~2 minutes, so it is not re-run here.
FORMERLY_LIVE_DATA_MODULES = (
    'tests.test_daily_eod_workflow', 'tests.test_daily_shape_public',
    'tests.test_industry_display_context', 'tests.test_m04_factor_evidence', 'tests.test_m05_selectors',
    'tests.test_m09_ledger', 'tests.test_market_cockpit', 'tests.test_market_external',
    'tests.test_market_public', 'tests.test_product_consolidation', 'tests.test_public_asset_limits',
    'tests.test_shared_contracts', 'tests.test_tracker_contract', 'tests.test_ui_v2_contract',
    'tests.test_eod_date_rollover',
)


def cboe(*days):
    return ('DATE,CLOSE\n' + ''.join(f'{d[5:7]}/{d[8:]}/{d[:4]},{15 + i}\n' for i, d in enumerate(days))).encode()


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class Bundle:
    """A temp repository root holding the frozen 23 Sep release."""

    def __init__(self, folder):
        self.root = Path(folder)
        self.public = self.root / 'public'
        self.public.mkdir()
        for path in PUBLIC_FIXTURE.glob('*.json'):
            shutil.copy(path, self.public / path.name)
        for path in PUBLIC_FIXTURE.glob('*.json.gz'):
            (self.public / path.name[:-3]).write_bytes(gzip.decompress(path.read_bytes()))
        (self.root / 'research').mkdir()
        shutil.copy(ROOT / 'research' / 'experiments.jsonl', self.root / 'research')
        internals = self.read('market-internals.json')
        market = self.root / 'data' / 'market'
        write(market / 'config-v1.json', internals['config'])
        for snapshot in internals['history']:
            write(market / internals['config']['series_id'] / 'snapshots' / f"{snapshot['date']}.json", snapshot)
        ranking = self.read('cr056-ranking.json')
        self.checkpoint({'as_of': ranking['as_of'], 'snapshot_fingerprint': ranking['source_snapshot'], 'symbols': {}})
        self.logic = internals['logic_fingerprint']

    def read(self, name):
        return json.loads((self.public / name).read_bytes())

    def write(self, name, payload):
        write(self.public / name, payload)

    def checkpoint(self, payload):
        path = self.root / 'automation' / 'cr056-watch-state.json.gz'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(payload).encode()))

    def check(self, as_of=DAY):
        # The checkpoint validator and the internals logic identity are
        # covered by their own unit tests; here they are pinned to the fixture.
        with patch('services.ledger.cr056.validate_watch_checkpoint', side_effect=lambda x: x), \
                patch('services.scanner.market_internals_daily.logic_fingerprint', return_value=self.logic):
            return check_release(as_of, root=self.root, public=self.public)

    # Realistic bad days: legitimate, validator-accepted content.
    def vix_and_vix9d_stale(self):
        self.external(lambda key: cboe('2026-09-21', '2026-09-22'))

    def one_cboe_source_unavailable(self):
        def fetch(key):
            if key == 'vix9d':
                raise OSError('Cboe download failed')
            return cboe('2026-09-22', DAY)
        self.external(fetch)

    def ishares_semiconductors_unavailable(self):
        radar = self.read('industry-radar.json')
        semi = next(t for t in radar['themes'] if t['theme_id'] == 'semiconductors')
        semi.update(source_status='unavailable', member_count=0, valid_member_count=0, state='Unavailable')
        radar['display_context']['funds']['SOXX']['available'] = False
        self.write('industry-radar.json', radar)

    def options_panel_missing(self):
        cockpit = self.read('market-cockpit.json')
        cockpit['panels']['options'] = {'id': 'options', 'frequency': 'daily', 'status': 'unavailable',
                                         'sources': [], 'observation_date': None, 'error_type': 'OSError'}
        self.write('market-cockpit.json', reseal(cockpit))

    def us_holiday_provider_date_unchanged(self):
        # No new session: the bundle stays on the provider's latest complete
        # date (23 Sep) while the calendar has moved on to 24 Sep.
        pass

    def external(self, fetcher):
        # A same-day output is reused by the producer, so rebuild from scratch.
        (self.public / 'market-external.json').unlink()
        with tempfile.TemporaryDirectory() as state:
            build_external(DAY, out=self.public / 'market-external.json', state=Path(state), fetcher=fetcher)


BAD_DAYS = ('vix_and_vix9d_stale', 'one_cboe_source_unavailable', 'ishares_semiconductors_unavailable',
            'options_panel_missing', 'us_holiday_provider_date_unchanged')


class ReleaseContractTests(unittest.TestCase):
    def bundle(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return Bundle(folder.name)

    def test_frozen_release_passes(self):
        errors, _ = self.bundle().check()
        self.assertEqual(errors, [])

    def test_bad_days_pass_with_visible_warnings(self):
        expected = {
            'vix_and_vix9d_stale': ['market-external: vix is stale', 'market-external: vix9d is stale'],
            'one_cboe_source_unavailable': ['market-external: vix9d is unavailable'],
            'ishares_semiconductors_unavailable': ['industry-radar: semiconductors membership unavailable', 'ETF context unavailable for SOXX'],
            'options_panel_missing': ['market-cockpit: options panel is unavailable'],
            'us_holiday_provider_date_unchanged': [],
        }
        for day in BAD_DAYS:
            with self.subTest(day=day):
                bundle = self.bundle()
                getattr(bundle, day)()
                errors, warnings = bundle.check()
                self.assertEqual(errors, [])
                for text in expected[day]:
                    self.assertTrue(any(text in w for w in warnings), (text, warnings))

    def test_holiday_release_is_gated_on_provider_date_not_calendar_date(self):
        errors, _ = self.bundle().check(as_of='2026-09-24')
        self.assertTrue(errors)
        self.assertTrue(all('2026-09-24' in e or 'date' in e.lower() or 'mismatch' in e.lower() for e in errors), errors)

    def test_genuinely_corrupt_data_is_rejected(self):
        def wrong_date(b):
            b.write('market-external.json', reseal(changed(b.read('market-external.json'), lambda p: p.update(as_of='2026-09-22'))))

        def bad_fingerprint(b):
            b.write('daily-shape-picker.json', changed(b.read('daily-shape-picker.json'), lambda p: p.update(purpose_zh='tampered')))

        def future_rows(b):
            b.write('market-internals.json', reseal(changed(b.read('market-internals.json'),
                    lambda p: p['history'].append(dict(p['history'][-1], date='2099-01-01')))))

        def resealed_internals_rewrite(b):
            internals = b.read('market-internals.json')
            snapshot = internals['history'][0]
            path = b.root / 'data' / 'market' / internals['config']['series_id'] / 'snapshots' / f"{snapshot['date']}.json"
            write(path, changed(snapshot, lambda s: s.update(fingerprint='sha256:' + '0' * 64)))

        def stale_status(b):
            b.write('update-status.json', changed(b.read('update-status.json'), lambda p: p.update(tracker_as_of='2026-09-22')))

        def checkpoint_mismatch(b):
            b.checkpoint({'as_of': DAY, 'snapshot_fingerprint': 'sha256:other', 'symbols': {}})

        def raw_bars_in_checkpoint(b):
            ranking = b.read('cr056-ranking.json')
            b.checkpoint({'as_of': DAY, 'snapshot_fingerprint': ranking['source_snapshot'],
                          'bars': [{'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}]})

        def semis_scored_without_members(b):
            radar = b.read('industry-radar.json')
            semi = next(t for t in radar['themes'] if t['theme_id'] == 'semiconductors')
            semi.update(valid_member_count=2, state='Leading')
            b.write('industry-radar.json', radar)

        def mixed_bundle_dates(b):
            b.write('signal-history-summary.json', changed(b.read('signal-history-summary.json'), lambda p: p.update(as_of='2026-09-22')))

        cases = {
            wrong_date: 'external_target_date_mismatch', bad_fingerprint: 'picker_content_hash_mismatch',
            future_rows: 'market_latest_missing', resealed_internals_rewrite: 'differs from its immutable snapshot',
            stale_status: 'same-day release', checkpoint_mismatch: 'reviewed ranking snapshot',
            raw_bars_in_checkpoint: 'raw OHLCV', semis_scored_without_members: 'fewer than 5 valid members',
            mixed_bundle_dates: 'release manifest',
        }
        for corrupt, message in cases.items():
            with self.subTest(case=corrupt.__name__):
                bundle = self.bundle()
                corrupt(bundle)
                errors, _ = bundle.check()
                self.assertTrue(any(message in e for e in errors), errors)

    def test_unit_suite_ignores_bad_day_public_assets(self):
        # Every bad day at once: each variant touches a different asset.
        bundle = self.bundle()
        for day in BAD_DAYS:
            getattr(bundle, day)()
        self.assertEqual(bundle.check()[0], [])
        read_bytes, read_text = Path.read_bytes, Path.read_text
        live = ROOT / 'public'

        def swap(path):
            path = Path(path)
            return bundle.public / path.name if path.parent == live and (bundle.public / path.name).exists() else path
        suite = unittest.defaultTestLoader.loadTestsFromNames(FORMERLY_LIVE_DATA_MODULES)
        result = unittest.TestResult()
        with patch.object(Path, 'read_bytes', lambda p: read_bytes(swap(p))), \
                patch.object(Path, 'read_text', lambda p, *a, **k: read_text(swap(p), *a, **k)):
            suite.run(result)
        problems = [f'{test.id()}: {trace.splitlines()[-1]}' for test, trace in result.failures + result.errors]
        self.assertEqual(problems, [])
        self.assertGreater(result.testsRun, 100)

if __name__ == '__main__':
    unittest.main()
