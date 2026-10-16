"""Synthetic-only checks for task 005."""
import copy
import unittest
from research.lab.account import run_account
from research.lab.decision import run_account_decision

S = dict(initial_cash=10000, allocation_fraction=.1, max_positions=10, cost_rate=.001, fractional_shares=False)


def trade(symbol, start=0, end=45, price=100, stop=90, priority=0):
    return dict(symbol=symbol, event_id=symbol, signal_date=str(start), entry_ci=start,
                entry_price=price, stop=stop, priority=priority,
                values=[price] * (end-start+1), exits=[(end, price, 1.)])


class DecisionTests(unittest.TestCase):
    def run_book(self, ts, decision=None, industry=None, scenario=None, rules=None, n=46):
        return run_account_decision(ts, n, scenario or S, rules, industry or {}, decision or {})

    def test_off_exact(self):
        ts = [trade('a'), trade('a', 1), trade('b', 2, price=12000), trade('c', 3)]
        ts[0]['exits'] = [(10, 110, .5), (45, 95, .5)]
        original = copy.deepcopy(ts)
        for fractional in (False, True):
            for rules in (None, dict(max_positions=1, position_cap=.2, risk_per_trade=.02, heat_cap=.1),
                          dict(max_positions=10, position_cap=.2, risk_per_trade=.02, heat_cap=.01)):
                s = dict(S, fractional_shares=fractional)
                self.assertEqual(self.run_book(ts, scenario=s, rules=rules), run_account(ts, 46, s, rules=rules))
        self.assertEqual(ts, original)

    def test_cap_and_unknown(self):
        ts = [trade(str(i)) for i in range(8)]
        out = self.run_book(ts, {'sector_cap': True}, {str(i): 'X' for i in range(4)})
        self.assertEqual(out['skipped'], {'sector_cap': 1})
        self.assertEqual(len(out['trades']), 7)
        self.assertEqual(out['decision']['positions'][0]['after_entries'], {'X': 3, 'UNKNOWN': 4})

    def test_gaps_start_day_and_stable_ties(self):
        ts = [trade('a'), trade('b', 1), trade('c', 1, priority=1), trade('d', 1, priority=2), trade('e', 2)]
        out = self.run_book(ts, {'gaps_first': True}, {'a':'X','b':'X','c':'Y','d':'Y','e':'Z'}, dict(S,max_positions=3))
        self.assertEqual([t['symbol'] for t in out['trades']], ['a','c','d'])
        self.assertEqual(out['decision']['positions'][0]['after_entries'], {'X':1})

    def test_swap_price_fee_once_and_no_later_exit(self):
        a = trade('a'); a['values'][40] = 80
        a['exits'] = [(45, 999, 1)]
        out = self.run_book([a,trade('b',40),trade('c',40)], {'swap':True}, scenario=dict(S,max_positions=1))
        swaps = out['decision']['swaps']
        self.assertEqual(len(swaps),1)
        self.assertEqual((swaps[0]['price'],swaps[0]['fee'],swaps[0]['previous_close_R']), (80,.8,0))
        self.assertEqual(out['trades'][0]['pnl'],-201.8)
        self.assertAlmostEqual(out['equity'][-1],9796.2)
        self.assertEqual(out['skipped'], {'position_limit':1})

    def test_previous_close_selects_not_today_or_future(self):
        a,b = trade('a'),trade('b')
        a['values'][39], b['values'][39] = 99, 101
        a['values'][40:], b['values'][40:] = [1000]*6, [1]*6
        out = self.run_book([a,b,trade('c',40)], {'swap':True}, scenario=dict(S,max_positions=2))
        self.assertEqual(out['decision']['swaps'][0]['event_id'],'a')
        self.assertAlmostEqual(out['decision']['swaps'][0]['previous_close_R'],-.1)

    def test_age_and_half_R_boundaries(self):
        for day, previous, count in ((39,100,0),(40,105,0),(40,104.9,1)):
            a=trade('a');a['values'][day-1]=previous
            out=self.run_book([a,trade('b',day)], {'swap':True},scenario=dict(S,max_positions=1))
            self.assertEqual(len(out['decision']['swaps']),count)

    def test_heat_does_not_trigger_swap(self):
        rules=dict(max_positions=10,position_cap=.2,risk_per_trade=.02,heat_cap=.02)
        out=self.run_book([trade('a'),trade('b',40)],{'swap':True},rules=rules)
        self.assertEqual(out['decision']['swaps'],[])
        self.assertEqual(out['skipped'],{'open_risk_limit':1})

    def test_cash_retry_can_fail_and_partial_exit_is_preserved(self):
        a=trade('a');a['exits']=[(20,100,.5),(45,999,.5)]
        a['values'][40]=1
        out=self.run_book([a,trade('b',40,price=20000)],{'swap':True})
        swap=out['decision']['swaps'][0]
        self.assertFalse(swap['replacement_entered'])
        self.assertEqual(swap['shares'],5)
        self.assertEqual(out['skipped'],{'cash_or_whole_share_insufficient':1})
        self.assertAlmostEqual(out['trades'][0]['pnl'],-496.505)


# The report script lives in the git-ignored work/ folder, so these checks run only where it exists (not on CI).
_REPORT = __import__("pathlib").Path(__file__).resolve().parents[1] / "work/v3w/decision_test.py"


@unittest.skipUnless(_REPORT.exists(), "work/v3w/decision_test.py is local-only")
class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        import sys
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / 'work/v3w'
        sys.path.insert(0, str(path))
        spec = importlib.util.spec_from_file_location('decision_test', path / 'decision_test.py')
        cls.report = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.report)

    def test_registered_verdict_boundaries(self):
        base = dict(decades={'2005-2014':.05, '2015-2025':.07})
        def summary(sh, dd, early=.05, late=.07):
            return dict(sharpe={'p50':sh},max_drawdown={'p50':dd},decades={'2005-2014':early,'2015-2025':late})
        for sh,dd in ((.684,.273),(.634,.243)):
            self.assertTrue(self.report.useful(summary(sh,dd),base)['useful'])
        self.assertFalse(self.report.useful(summary(.683,.273),base)['useful'])
        self.assertFalse(self.report.useful(summary(.633,.243),base)['useful'])
        self.assertFalse(self.report.useful(summary(.7,.2,early=.039),base)['useful'])
        self.assertFalse(self.report.useful(summary(.7,.2,late=.059),base)['useful'])

    def test_hindsight_partial_whole_shares_and_fees(self):
        t=trade('a');t['exits']=[(20,110,.5),(45,90,.5)]
        swap=dict(original_shares=5,original_cost=500.5)
        expected=round((2*110+3*90)*.999/500.5-1,6)/.1
        self.assertAlmostEqual(self.report.held_R(swap,t,.001),expected)
        t['exits']=[]
        self.assertIsNone(self.report.held_R(swap,t,.001))

    def test_decade_preserves_previous_nav(self):
        from unittest.mock import patch
        seen=[]
        def stats(equity,dates,initial):
            seen.append((equity,dates,initial));return {'cagr':0}
        with patch.object(self.report.account,'curve_stats',side_effect=stats):
            self.report.decade_cagr([100,120,150],['2014-12-30','2014-12-31','2015-01-02'],90)
        self.assertEqual(seen[1],([150],['2015-01-02'],120))


if __name__ == '__main__':
    unittest.main()
