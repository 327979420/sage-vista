"""Guard: tests must not read the moving daily public/ output.

Twice (21/23 Sep and 28-30 Sep 2026) a test that rendered or asserted the day's
generated public/*.json blocked every EOD release. Tests use the frozen snapshot
in tests/fixtures/public-2026-09-23 (tests/public_fixture.py and
tests/helpers/public-fixture.mjs); live-data checks belong in
services/scanner/release_contract.py or services/automation/report_untranslated.mjs.
"""
import pathlib
import re
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
WORKFLOW = TESTS.parent / '.github/workflows/daily-eod.yml'

# Files that may name a daily asset next to "public", and why that is safe.
ALLOWED = {
    'test_daily_eod_workflow.py': 'asserts workflow text and builds temp bundles',
    'test_opportunity_ledger_workflow.py': 'asserts workflow text',
    'test_universe_snapshot.py': 'only checks the files are left unchanged',
    'test_industry_radar.py': 'only checks the tracker is left unchanged',
    'test_ui_v2_contract.py': 'only checks the ledger file exists',
    'test_release_contract.py': 'serves bad-day bundles in place of public/',
    'test_market_data_consumers.py': 'reads a file pinned to a historical git commit',
    'test_shared_contracts.py': 'uses a public path only as an unsafe-path rejection case',
    'test_tests_use_frozen_data.py': 'this guard',
}


def daily_assets():
    commit = WORKFLOW.read_text().split('name: Commit audited website data', 1)[1].split('      - name:', 1)[0]
    return sorted(set(re.findall(r'public/([\w.-]+\.json(?:\.gz)?)', commit)))


class FrozenTestDataTests(unittest.TestCase):
    def test_daily_asset_list_is_read_from_the_workflow(self):
        self.assertIn('cr056-ranking.json', daily_assets())
        self.assertIn('market-cockpit.json', daily_assets())

    def test_no_test_reads_the_daily_public_output(self):
        names = '|'.join(re.escape(n) for n in daily_assets())
        # A daily asset named next to public, or any public path built at runtime.
        live = re.compile(r"""public['"]?\s*/\s*['"]?(%s)|public/(%s)|public/?\$\{""" % (names, names))
        offenders = []
        for path in sorted(TESTS.glob('*.py')) + sorted(TESTS.glob('*.mjs')):
            if path.name in ALLOWED:
                continue
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if live.search(line):
                    offenders.append(f'{path.name}:{number}: {line.strip()[:120]}')
        self.assertEqual(offenders, [], 'Use the frozen fixture (tests/public_fixture.py or tests/helpers/public-fixture.mjs) instead of live public/ data')


if __name__ == '__main__':
    unittest.main()
