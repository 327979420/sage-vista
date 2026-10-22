import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.lab import trade_review as R, forward_judge as J, own_picks as P
from tests.test_own_picks import fixture, pick
from tests.test_forward_judge import fixture as forward_fixture


def alert():
    return {'id': 'alert-1', 'symbol': 'TEST', 'entry': 100., 'exit': 130., 'stop': 90., 'target': 130.,
            'planned_entry': 100., 'planned_stop': 90., 'planned_target': 130.,
            'opened': '2026-10-05', 'closed': '2026-10-16', 'net_R': J.net_r(100,130,90),
            'twin_net_R': .2, 'verified': True}


def position(**kwargs):
    return {'id': 'real-1', 'account': 'real', 'symbol': 'TEST', 'source': '3W', 'qty': 10,
            'entry': 102., 'stop': 95., 'target': 130., 'opened': '2026-10-05', 'closed': '2026-10-15',
            'status': 'closed', 'last': 110., 'exit_price': 110., 'exit_reason': 'manual', 'alert_id': 'alert-1',
            'stop_history': [{'date':'2026-10-05','stop':90.}, {'date':'2026-10-09','stop':95.}], **kwargs}


def own_review(status):
    px = fixture()
    p = pick(px)
    s = px['TEST']
    if status == 'win':
        s['high'][503] = 131.
    elif status == 'loss':
        s['open'][503] = 85.
        s['low'][503] = 84.
    as_of = s['date'][-1]
    cards, _ = R.replay_cards({'synthetic': px}, [], [], {}, [p], as_of)
    return px, p, cards[0]


class ReviewTests(unittest.TestCase):
    def test_all_engine_exit_reasons(self):
        for status, reason in [('win','target'), ('loss','stop'), ('time','time')]:
            with self.subTest(status=status):
                px, p, c = own_review(status)
                trade = P.replay(px['TEST'], p)
                self.assertEqual(c['reason'], reason)
                self.assertEqual(c['net_R'], trade['net_R'])
                self.assertEqual(c['holding_days'], trade['exit_day']-trade['fill_day']+1)

    def test_gap_stop_uses_fill_not_stop(self):
        _, _, c = own_review('loss')
        self.assertEqual(c['exit'], 85.)
        self.assertAlmostEqual(c['net_R'], -1.5185)

    def test_manual_exit(self):
        cards, _ = R.cockpit_cards({'positions':[position()]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(cards[0]['reason'], 'manual')
        self.assertAlmostEqual(cards[0]['net_R'], (110*.999-102*1.001)/12)

    def test_slippage_sign_and_plan_unit(self):
        for fill, percent, risk in [(102,2,.2),(98,-2,-.2),(100,0,0)]:
            c = {'entry':fill, 'planned_entry':100.,'planned_stop':90.}
            R.slippage(c)
            self.assertAlmostEqual(c['slippage_pct'], percent)
            self.assertAlmostEqual(c['slippage_R'], risk)

    def test_mfe_mae_and_spy(self):
        q = {'date':['2026-10-05','2026-10-06','2026-10-07'], 'open':[100.,104.,105.],
             'high':[106.,120.,111.], 'low':[99.,95.,100.], 'close':[104.,105.,110.]}
        c = {'opened':q['date'][0], 'closed':q['date'][-1], 'entry':100., 'stop':90.}
        R.market_context(c,q,q,'2026-10-07')
        self.assertEqual((c['mfe_R'], c['mae_R'], c['holding_days']), (2.,-.5,3))
        self.assertAlmostEqual(c['spy_return'],110/104-1)

    def test_missing_session_not_padded(self):
        q = {'date':['2026-10-05','2026-10-07'], 'open':[100.,100.], 'high':[110.,110.],
             'low':[99.,99.], 'close':[105.,105.]}
        c = {'opened':'2026-10-05','closed':'2026-10-07','entry':100.,'stop':90.}
        R.market_context(c,q,None,'2026-10-07')
        self.assertIsNone(c['holding_days'])
        self.assertIsNone(c['mfe_R'])
        self.assertIsNone(c['spy_return'])

    def test_deviations_each_kind_and_one_impact(self):
        cards, ds = R.cockpit_cards({'positions':[position()]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(cards[0]['deviations'], ['成交价格不同','移动止损','提前退出'])
        self.assertEqual(len(ds), 1)
        expected = ((110*.999-102*1.001)-(130*.999-100*1.001))/10
        self.assertAlmostEqual(ds[0]['impact_R'], expected)
        self.assertNotAlmostEqual(ds[0]['impact_R'], ds[0]['actual_net_R']-ds[0]['alert_net_R'])

    def test_each_deviation_in_isolation(self):
        base = position(entry=100.,closed='2026-10-16',exit_price=130.,stop_history=[{'date':'2026-10-05','stop':90.}])
        cases = [({'entry':101.}, '成交价格不同'),
                 ({'closed':'2026-10-15'}, '提前退出'),
                 ({'stop_history':position()['stop_history']}, '移动止损')]
        for changes, kind in cases:
            cards, ds = R.cockpit_cards({'positions':[{**base, **changes}]}, {'alert-1':alert()}, {}, '2026-10-16')
            self.assertEqual(cards[0]['deviations'], [kind])
            self.assertEqual(ds[0]['kind'],kind)

    def test_skip_zero_pnl_and_never_inferred(self):
        _, ds = R.cockpit_cards({'positions':[]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(ds, [])
        cards, ds = R.cockpit_cards({'skips':[{'alert_id':'alert-1','skipped':True,'date':'2026-10-05','note':'已记录'}]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(cards, [])
        self.assertAlmostEqual(ds[0]['impact_R'], -2.977)

    def test_unknown_or_unfinished_alert_impact_missing(self):
        for a in (None, {**alert(),'verified':False}, {**alert(),'exit':None}):
            self.assertIsNone(R.impact({'entry':102.,'exit':110.},a))

    def test_missing_fields_not_inferred(self):
        p = position()
        for k in ('closed','alert_id','exit_reason','stop_history'):
            p.pop(k)
        cards, ds = R.cockpit_cards({'positions':[p]}, {'alert-1':alert()}, {}, '2026-10-16')
        c=cards[0]
        for key in ('closed','reason','net_R','planned_entry','twin_net_R','holding_days','impact_R'):
            self.assertIsNone(c[key], key)
        self.assertEqual(ds, [])
        report=R.digest(cards,ds,'2026-10-16','已提供')
        self.assertEqual(report['totals']['real/3W']['count'],0)
        self.assertEqual(len(report['undated']),1)
        self.assertIn('缺数据', R.render(report))

    def test_history_after_exit_not_counted(self):
        p=position(entry=100.,closed='2026-10-16',stop_history=[{'date':'2026-10-05','stop':90.},{'date':'2026-10-19','stop':99.}])
        cards,_=R.cockpit_cards({'positions':[p]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(cards[0]['deviations'],[])

    def test_symbol_mismatch_refused(self):
        with self.assertRaises(ValueError):
            R.cockpit_cards({'positions':[position(symbol='OTHER')]}, {'alert-1':alert()}, {}, '2026-10-16')

    def test_no_twins_still_counted(self):
        cards,_=R.cockpit_cards({'positions':[position(source='manual',alert_id=None)]}, {}, {}, '2026-10-16')
        self.assertIsNone(cards[0]['twin_net_R'])
        self.assertEqual(R.totals(cards)['count'],1)
        self.assertEqual(R.totals(cards)['paired_count'],0)
        self.assertIsNone(R.totals(cards)['vs_twins'])

    def test_frozen_recompute_reused_and_immutable(self):
        px, rec=forward_fixture()
        rec['dataset']='synthetic'
        pool=[s for s in px if s != 'TEST']
        with patch.object(J.F,'PX',px):
            frozen=J.F.outcome(rec,pool)
        before=copy.deepcopy((px,rec,frozen))
        expected=J.recompute(px,[rec],[frozen],{})[0]
        with patch.object(J,'recompute',wraps=J.recompute) as fn:
            cards,alerts=R.replay_cards({'synthetic':px},[rec],[frozen],{},[],px['TEST']['date'][-1])
        fn.assert_called_once()
        self.assertEqual((px,rec,frozen),before)
        self.assertEqual(cards[0]['net_R'],expected['trade']['net_R'])
        self.assertEqual(cards[0]['twin_net_R'],expected['net_twin_mean'])
        self.assertEqual(set(cards[0]['checks'].values()),{'一致'})
        self.assertTrue(alerts[rec['id']]['verified'])

    def test_mismatch_suppresses_results(self):
        px, rec=forward_fixture(); rec['dataset']='synthetic'
        frozen={'id':rec['id'],'r19':{'status':'time','R':999.}}
        cards,alerts=R.replay_cards({'synthetic':px},[rec],[frozen],{},[],px['TEST']['date'][-1])
        self.assertIsNone(cards[0]['net_R'])
        self.assertIsNone(cards[0]['twin_net_R'])
        self.assertFalse(alerts[rec['id']]['verified'])

    def test_own_compute_reused(self):
        px=fixture(); p=pick(px)
        with patch.object(P,'compute',wraps=P.compute) as fn:
            cards,_=R.replay_cards({'synthetic':px},[],[],{},[p],px['TEST']['date'][-1])
        fn.assert_called_once()
        self.assertEqual(len(cards),1)
        # Market order has no planned numeric fill: do not pretend ref is a limit.
        self.assertIsNone(cards[0]['planned_entry'])

    def test_paper_frozen_match_and_mismatch(self):
        p=position(account='paper',entry=100.,closed='2026-10-16',exit_price=130.,stop_history=[{'date':'2026-10-05','stop':90.}])
        cards,_=R.cockpit_cards({'positions':[p]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(set(cards[0]['checks'].values()),{'一致'})
        cards,_=R.cockpit_cards({'positions':[{**p,'target':120.}]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(cards[0]['checks']['3R目标'],'不同')

    def test_chart_window_and_asof(self):
        px,p,c=own_review('win')
        q=px['TEST']
        self.assertEqual((c['before'],c['after']),(60,20))
        self.assertEqual(len(c['bars']),60+c['holding_days']+20)
        info=R.period_data(q,c['opened'],c['closed'],c['closed'])
        self.assertEqual(info['after'],0)
        self.assertEqual(info['bars'][-1]['date'],c['closed'])
        svg=R.chart(c)
        for label in ('入场','止损','目标','退出'):
            self.assertIn(label,svg)
        self.assertNotIn('http',svg)

    def test_week_and_cumulative_boundaries(self):
        base={'group':'3W前向','net_R':1.,'twin_net_R':.25}
        cards=[{**base,'closed':d} for d in ('2026-10-09','2026-10-12','2026-10-16','2026-10-19')]
        r=R.digest(cards,[],'2026-10-16','未提供')
        self.assertEqual(len(r['cards']),2)
        self.assertEqual(r['totals']['3W前向']['count'],3)
        self.assertEqual(r['future_excluded'],1)
        self.assertEqual(r['totals']['3W前向']['vs_twins'],.75)

    def test_aggregate_hand_values(self):
        cards=[{'net_R':v,'twin_net_R':None} for v in (2.,-1.,0.,None)]
        t=R.totals(cards)
        self.assertEqual((t['count'],t['net_count']),(4,3))
        self.assertEqual((t['payoff'],t['profit_factor']),(2.,2.))
        self.assertAlmostEqual(t['mean_net_R'],1/3)
        self.assertAlmostEqual(t['win_rate'],1/3)

    def test_empty_week_render(self):
        report=R.digest([],[],'2026-10-16','未提供')
        page=R.render(report)
        for text in ('本周无已结束交易','未提供','无已记录偏差','实际每股净盈亏','提醒风险'):
            self.assertIn(text,page)
        self.assertNotIn('<script',page)
        self.assertNotIn('nan',page)
        self.assertEqual(len(report['totals']),8)
        json.dumps(report,allow_nan=False)

    def test_empty_week_preserves_running_totals(self):
        c={'group':'3W前向','closed':'2026-10-09','net_R':1.,'twin_net_R':None}
        r=R.digest([c],[],'2026-10-16','未提供')
        self.assertEqual(r['cards'],[])
        self.assertEqual(r['totals']['3W前向']['count'],1)

    def test_html_escapes_export_values(self):
        cards,ds=R.cockpit_cards({'positions':[position(symbol='<script>alert(1)</script>',alert_id=None)]}, {}, {}, '2026-10-16')
        page=R.render(R.digest(cards,ds,'2026-10-16','已提供'))
        self.assertNotIn('<script>',page)
        self.assertIn('&lt;script&gt;',page)

    def test_cli_missing_cockpit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            with patch.object(R,'load_inputs',return_value=({},[],[],{'datasets':[]},[])):
                R.main(['--as-of','2026-10-16','--cockpit',str(folder/'absent.json'),'--out',str(folder)])
            report=json.loads((folder/'weekly-2026-10-16.json').read_text())
            self.assertEqual(report['cockpit_status'],'未提供')
            self.assertTrue((folder/'weekly-2026-10-16.html').exists())

    def test_missing_own_prices_explicit_unknown(self):
        px=fixture(); p=pick(px)
        cards,_=R.replay_cards({},[],[],{},[p],px['TEST']['date'][-1])
        self.assertEqual(len(cards),1)
        self.assertIsNone(cards[0]['net_R'])
        self.assertIsNone(cards[0]['closed'])
        self.assertIn('无法确定是否结束',cards[0]['check'])

    def test_no_future_alert_result_for_skip(self):
        _,ds=R.cockpit_cards({'skips':[{'alert_id':'alert-1','skipped':True,'date':'2026-10-05'}]},
                             {'alert-1':alert()}, {}, '2026-10-09')
        self.assertIsNone(ds[0]['impact_R'])
        self.assertIsNone(ds[0]['alert_net_R'])

    def test_paper_moved_stop_detected(self):
        cards,_=R.cockpit_cards({'positions':[position(account='paper')]}, {'alert-1':alert()}, {}, '2026-10-16')
        self.assertEqual(cards[0]['checks']['止损'],'不同')

    def test_nonpositive_risk_is_missing(self):
        self.assertIsNone(R.net_r(85,85,90))
        self.assertIsNone(R.impact({'entry':102.,'exit':110.},{**alert(),'stop':100.}))

    def test_skip_comparison_appears_when_alert_finishes(self):
        _,ds=R.cockpit_cards({'skips':[{'alert_id':'alert-1','skipped':True,'date':'2026-10-05'}]},
                             {'alert-1':alert()}, {}, '2026-10-16')
        report=R.digest([],ds,'2026-10-16','已提供')
        self.assertEqual(len(report['deviations']),1)
        self.assertEqual(report['deviations'][0]['comparison_date'],'2026-10-16')
        self.assertAlmostEqual(report['deviations'][0]['impact_R'],-2.977)

    def test_missing_cache_and_integrity_error_distinguished(self):
        cockpit={'positions':[position()]}
        with patch.object(J,'cached_prices',side_effect=FileNotFoundError):
            prices,*_=R.load_inputs('2026-10-19',cockpit)
        self.assertTrue(prices)
        self.assertTrue(all(px == {} for px in prices.values()))
        with patch.object(J,'cached_prices',side_effect=ValueError('SHA mismatch')):
            with self.assertRaisesRegex(ValueError,'SHA mismatch'):
                R.load_inputs('2026-10-19',cockpit)

    def test_prices_capped_at_frozen_run(self):
        q={'date':['2026-10-16','2099-01-01'],'open':[100.,999.],'high':[101.,999.],
           'low':[99.,999.],'close':[100.,999.]}
        with patch.object(J,'cached_prices',return_value={'TEST':q}):
            prices,*_=R.load_inputs('2026-10-19',{'positions':[position()]})
        for px in prices.values():
            self.assertEqual(px['TEST']['date'],['2026-10-16'])

    def test_own_price_gap_is_visible_not_guessed(self):
        px=fixture(); p=pick(px)
        for values in px['TEST'].values():
            del values[502]
        cards,_=R.replay_cards({'synthetic':px},[],[],{},[p],px['TEST']['date'][-1])
        self.assertIsNone(cards[0]['closed'])
        self.assertIsNone(cards[0]['net_R'])
        self.assertIn('缺数据',cards[0]['check'])


if __name__ == '__main__':
    unittest.main()
