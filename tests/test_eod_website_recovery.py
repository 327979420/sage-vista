"""CR-055: real failing branch and website-only workflow permission boundaries."""
import copy
import hashlib
from itertools import combinations, product
import json
from pathlib import Path
import re
import tempfile
import unittest

from services.scanner.factor_registry import FACTORS_BY_ID
from services.scanner.unified_v2_scan import _timeframe_profile, run_published
from tests.test_unified_v2_scan import state

ROOT = Path(__file__).resolve().parents[1]


class EodWebsiteRecoveryTests(unittest.TestCase):
    def test_empty_period_preserves_resonance_input_and_reports_insufficient(self):
        for ids in ([], ['not-a-real-factor']):
            if ids:  # Unknown factor remains an error, not invented evidence.
                with self.assertRaises(KeyError):
                    _timeframe_profile([], {}, dict(positive_factor_ids=ids))
                continue
            resonance = dict(positive_factor_ids=ids, timeframe_resonance_bonus=0, timeframe_resonances=[])
            before = copy.deepcopy(resonance)
            result = _timeframe_profile([], {}, resonance)
            self.assertIsNone(result['dominant_timeframe'])
            self.assertFalse(result['is_resonance'])
            self.assertEqual(result['label'], '周期证据不足')
            self.assertEqual(result['resonance_bonus'], 0)
            self.assertEqual(result['resonances'], [])
            self.assertEqual(resonance, before)

    def test_all_nonempty_period_combinations_preserve_main_bytes(self):
        ids = ['support.ema_proximity', 'support.weekly_ema_proximity', 'support.monthly_ema_proximity']
        values = [_timeframe_profile([], {}, dict(positive_factor_ids=list(c),
            timeframe_resonance_bonus=2, timeframe_resonances=[]))
            for n in range(1, 4) for c in combinations(ids, n)]
        # Captured from unmodified main 14fef535 before this fix.
        self.assertEqual(hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                         '8e84ac25ed1850b74f4adb555fed6407846519f22ea5c78537f5a54153311b3d')

    def test_run_published_keeps_zero_evidence_candidate_and_rejects_wrong_date(self):
        day = '2026-09-04'
        rows = []
        for symbol, extra in [('EMPTY', set()), ('NORMAL', {'support.ema_proximity'})]:
            hits = {'qualification.long_trend', 'macd.daily_bull_cross'} | extra
            rows.append(dict(symbol=symbol, price=20,
                trigger={'factor_id': 'macd.daily_bull_cross', 'exact_completed_cross': True},
                factors=[state(key, key in hits, key in hits) for key in FACTORS_BY_ID],
                scoring={'experimental_observational_score': 0}))
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name, value in {
                'daily-factor-snapshot.json': {'as_of': day, 'eligible_count': 2, 'symbols': rows},
                'market-etf-watch.json': {'as_of': day, 'market_temperature': {'score': 3, 'state': 'neutral'}},
                'industry-radar.json': {'as_of': day, 'historical_membership_safe': False},
            }.items():
                (p / name).write_text(json.dumps(value))
            report = run_published(out=p/'rankings.json', public_dir=p)
            ranking = report['days'][0]['ranking']
            self.assertEqual([(r['symbol'], r['rank']) for r in ranking], [('NORMAL', 1), ('EMPTY', 2)])
            self.assertEqual(ranking[1]['technical_score'], 0)
            self.assertFalse(ranking[1]['timeframe_profile']['is_resonance'])
            original = (p/'rankings.json').read_bytes()
            (p/'industry-radar.json').write_text(json.dumps({'as_of': '2026-09-03'}))
            with self.assertRaisesRegex(RuntimeError, 'not synchronized'):
                run_published(out=p/'rankings.json', public_dir=p)
            self.assertEqual((p/'rankings.json').read_bytes(), original)

    def test_notification_effects_require_explicit_manual_opt_in(self):
        text = (ROOT/'.github/workflows/daily-eod.yml').read_text()
        self.assertRegex(text, r'notify:\n(?:        [^\n]+\n)*        default: false\n        type: boolean')
        global_env = text.split('    steps:', 1)[0]
        self.assertNotIn('DISCORD_WEBHOOK_URL', global_env)
        blocks = {block.splitlines()[0]: block for block in text.split('      - name: ')[1:]}
        notification_names = ['Dry-run Discord payload', 'Validate dry-run did not send',
            'Require explicitly requested notification secret', 'Send deduplicated Discord daily digest',
            'Validate Discord send result', 'Persist Discord duplicate state']
        for name in notification_names:
            condition = re.search(r'^        if: (.+)$', blocks[name], re.M).group(1)
            self.assertTrue(condition.startswith("github.event_name == 'workflow_dispatch' && inputs.notify == true && "))
            # Check each real condition for scheduled/recovery/manual default,
            # explicit notification and failed verification combinations.
            for event, notify, success in product(('schedule', 'workflow_dispatch'), (False, True), (False, True)):
                expr = condition.replace("github.event_name", repr(event)).replace('inputs.notify == true', str(notify))
                expr = expr.replace('&&', 'and')
                result = ('true' if success else 'false') if 'needs_release' in condition else ('success' if success else 'failure')
                expr = re.sub(r'steps\.[\w.]+', repr(result), expr)
                allowed = eval(expr, {'__builtins__': {}}, {})
                self.assertEqual(allowed, event == 'workflow_dispatch' and notify and success, name)
                if event != 'workflow_dispatch' or not notify:
                    self.assertFalse(allowed, name)
        for name in ('Require deployment secrets', 'Deploy production to Cloudflare Workers', 'Verify live Cloudflare dates and audits'):
            self.assertNotIn('inputs.notify', blocks[name])
            self.assertNotIn('DISCORD_WEBHOOK_URL', blocks[name])
        self.assertIn("steps.live_verify.outcome == 'success'", blocks['Send deduplicated Discord daily digest'])
