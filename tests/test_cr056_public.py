import copy
import unittest
from services.contracts.market_data import canonical_fingerprint
from services.scanner.cr056_public import project_report, project_details

class PublicProjectionTests(unittest.TestCase):
    def test_projection_copies_scores_and_order_without_private_facts(self):
        score={'total_score':42.125, 'coverage':1, 'high_score_eligible':False,
               'timeframes':{tf:{'normalized':v,'groups':[]} for tf,v in
                              [('daily',.1),('weekly_completed',.7),('monthly_completed',.2)]}}
        report={'result_role':'legacy_comparison','as_of':'2026-09-04','policy_version':'candidate','policy_fingerprint':'sha256:'+'1'*64,
                'code_commit':'fixed', 'input_coverage':{},'counts':{},'ranked_symbols':['AAA'],
                'selected_symbols':['AAA'],'new_nomination_symbols':[], 'continuing_ranked_symbols':['AAA'],
                'reviews':[{'symbol':'AAA','rank':1,'score':score,'permission':{},'reason_codes':[],
                            'entry_gate':{'paths':[{'path':'bottom_macd','timeframe':'daily',
                                'confirmed_through':'2026-09-04','cross_date':'2026-09-04',
                                'structure_key':'never publish','structure_floor':10}]},
                            'factor_states':[{'raw_private':'never publish'}], 'input_fingerprint':'private',
                            'origin':{'date':'2026-08-28','original_record':{'legacy_private':'never publish'}}}]}
        report['reviews'][0]['permission']={'checks':{'structure':{'status':'blocked','reason':'structure_broken'}}}
        report['reviews'][0]['entry_tracking']={'records':[{'path':'bottom_macd','timeframe':'daily',
            'trigger_date':'2026-09-04','structure_floor':10,'state':'active','invalidated_at':None}],
            'history_start':'2026-09-04','as_of':'2026-09-04'}
        report['snapshot_fingerprint']=canonical_fingerprint(report)
        before=copy.deepcopy(report); public=project_report(report)
        self.assertEqual(report,before)
        details=project_details(report)['reviews']['AAA']
        self.assertEqual(details['checks']['structure']['status'],'blocked')
        self.assertEqual(details['structures'][0]['structure_floor'],10)
        self.assertEqual(report,before)
        self.assertEqual(public['reviews'][0]['total'],42.125)
        self.assertEqual(public['ranked_symbols'],['AAA'])
        self.assertEqual(public['policy_fingerprint'],report['policy_fingerprint'])
        self.assertNotIn('never publish',str(public))
        self.assertNotIn('new_nomination',public['reviews'][0])
        self.assertNotIn('high_score_eligible',public['reviews'][0])
        affirmative=copy.deepcopy(report)
        affirmative['reviews'][0]['new_nomination']=True
        affirmative['reviews'][0]['score']['high_score_eligible']=True
        affirmative.pop('snapshot_fingerprint')
        affirmative['snapshot_fingerprint']=canonical_fingerprint(affirmative)
        flags=project_report(affirmative)['reviews'][0]
        self.assertTrue(flags['new_nomination'])
        self.assertTrue(flags['high_score_eligible'])
        report['reviews'][0]['score']['total_score']=99
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            project_report(report)

class NominationObservationTests(unittest.TestCase):
    def test_return_starts_at_nomination_not_an_older_gate(self):
        from services.scanner.cr056_runner import nomination_observation
        rows=[{'date':'2019-08-01','close':10.}, {'date':'2026-04-13','close':100.}, {'date':'2026-09-08','close':120.}]
        result=nomination_observation(rows,{'date':'2026-04-13'},'2026-09-08')
        self.assertEqual(result['date'],'2026-04-13')
        self.assertEqual(result['price'],100.)
        self.assertAlmostEqual(result['price_change'],.2)
        self.assertEqual(nomination_observation(rows,{'date':'2026-09-08'},'2026-09-08')['price_change'],0.)

    def test_missing_nomination_close_is_not_replaced_with_nearest_or_old_gate(self):
        from services.scanner.cr056_runner import nomination_observation
        result=nomination_observation([{'date':'2026-09-08','close':120.}],{'date':'2026-04-13'},'2026-09-08')
        self.assertIsNone(result['price_change']);self.assertIsNone(result['price'])
        self.assertEqual(result['status'],'nomination_close_unavailable')
