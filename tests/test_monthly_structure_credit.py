import unittest
from unittest.mock import patch
from services.scanner.detectors import head_shoulders_bottom, multi_bottom_structure
from services.scanner.macd_factor_backtest import three_push_structure_state
from services.ranking.cr056 import score_candidate
from tests.test_cr056_strategy import states, facts
from services.selectors.cr056 import assess_permission


def candles():
    values=[14,13,12,11,10,12,14,15,13,10,8,10,13,15,14,12,10,11,12]
    return [dict(date=f'2020-01-{i+1:02}',open=v+.3,close=v+.5,low=v,high=v+1,volume=1000) for i,v in enumerate(values)]

class StructureCreditTests(unittest.TestCase):
    def test_forming_confirmed_invalidated_and_no_resurrection(self):
        rows=candles(); state=head_shoulders_bottom(rows)
        self.assertEqual(state['stage'],'forming'); self.assertEqual(state['strength'],.5)
        rows.append(dict(date='2020-01-20',open=15,close=18,low=14,high=19,volume=1000))
        self.assertEqual(head_shoulders_bottom(rows)['stage'],'confirmed')
        rows.append(dict(date='2020-01-21',open=9,close=7,low=6,high=10,volume=1000))
        rows.append(dict(date='2020-01-22',open=10,close=18,low=9,high=19,volume=1000))
        self.assertEqual(head_shoulders_bottom(rows)['stage'],'invalidated')
        self.assertEqual(head_shoulders_bottom(rows)['strength'],0)

    def test_multiple_bottom_state_survives_confirmation_day(self):
        rows=candles(); rows[10]['low']=9.5
        rows.extend(dict(date=f'2020-02-{i+1:02}',open=12,close=13,low=12,high=14,volume=1000) for i in range(5))
        state=multi_bottom_structure(rows)
        self.assertEqual(state['stage'],'forming')
        self.assertEqual(state['strength'],.5)
        self.assertLess(state['confirmed_at'],rows[-1]['date'])
        rows[-2]['close']=9
        self.assertEqual(multi_bottom_structure(rows)['stage'],'invalidated')

    def test_no_future_confirmation(self):
        rows=candles(); before=head_shoulders_bottom(rows,15)
        future=rows+[dict(date='2020-01-20',open=100,close=100,low=1,high=200,volume=1)]
        self.assertEqual(head_shoulders_bottom(future,15),before)
        self.assertNotEqual(before['stage'],'forming')

    def test_ordinary_higher_lows_are_not_head_shoulders(self):
        rows=candles(); rows[10]['low']=11
        self.assertEqual(head_shoulders_bottom(rows)['strength'],0)

    def test_partial_credit_and_bottom_group_dedup(self):
        base=states()
        for s in base:s.update(hit=False,recent_hit=False,value=0)
        fid='monthly_completed::structure.head_shoulders_bottom'
        next(s for s in base if s['factor_id']==fid).update(hit=True,value=.5)
        p=assess_permission(facts())
        def group():
            r=score_candidate(base,p)
            return next(g for g in r['timeframes']['monthly_completed']['groups'] if fid in g['factor_ids'])
        self.assertEqual(group()['contribution'],.5)
        next(s for s in base if s['factor_id']==fid)['value']=1
        self.assertEqual(group()['contribution'],1)
        next(s for s in base if s['factor_id']=='monthly_completed::structure.double_bottom').update(hit=True,value=1)
        self.assertEqual(group()['contribution'],1)

    def test_three_push_ignores_minor_peak_without_losing_main_line(self):
        from services.scanner.macd_factor_backtest import three_push_breakout_setup
        rows=[dict(date=f'D{i}',open=95,high=96,low=94,close=95,volume=1000) for i in range(80)]
        for i,p in ((20,110),(35,106),(45,99),(50,102)):
            rows[i].update(high=p,close=p-2,open=p-3,low=p-4)
        rows[55].update(open=98,high=103,low=97,close=102.5)
        setup=three_push_breakout_setup(rows,55)
        self.assertEqual([a['date'] for a in setup['anchors']],['D20','D35','D50'])
        rows[60].update(high=999,close=999)
        self.assertEqual(three_push_breakout_setup(rows,55),setup)
        rows[40]['high']=120
        self.assertIsNone(three_push_breakout_setup(rows,55))

    def test_three_push_keeps_old_breakout_and_invalidates(self):
        rows=candles()
        rows.extend(dict(date=f'2020-02-{i+1:02}',open=13,close=14,low=13,high=15,volume=1000) for i in range(15))
        rows[18].update(open=14,close=16,high=17)
        setup={'level':15,'slope':-.1,'atr':1}
        points={'highs':[{'index':1,'price':20},{'index':6,'price':18},{'index':13,'price':16}],
                'lows':[{'index':4,'price':10},{'index':10,'price':8}]}
        with patch('services.scanner.macd_factor_backtest.three_push_breakout_setup',side_effect=lambda r,j:setup if j==18 else None),patch('services.scanner.macd_factor_backtest.pivots',return_value=points):
            state=three_push_structure_state(rows)
            self.assertEqual(state['breakout_date'],'2020-01-19')
            self.assertEqual(state['strength'],1)
            rows[-2]['close']=7
            self.assertEqual(three_push_structure_state(rows)['strength'],0)

if __name__=='__main__':unittest.main()
