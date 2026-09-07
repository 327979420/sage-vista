import copy
import unittest
from services.contracts.market_data import canonical_fingerprint
from services.scanner.cr056_public import project_report

class PublicProjectionTests(unittest.TestCase):
    def test_projection_copies_scores_and_order_without_private_facts(self):
        score={'total_score':42.125, 'coverage':1, 'high_score_eligible':False,
               'timeframes':{tf:{'normalized':v,'groups':[]} for tf,v in
                              [('daily',.1),('weekly_completed',.7),('monthly_completed',.2)]}}
        report={'result_role':'legacy_comparison','as_of':'2026-09-04','policy_version':'candidate',
                'code_commit':'fixed', 'input_coverage':{},'counts':{},'ranked_symbols':['AAA'],
                'selected_symbols':['AAA'],'new_nomination_symbols':[], 'continuing_ranked_symbols':['AAA'],
                'reviews':[{'symbol':'AAA','rank':1,'score':score,'permission':{},'reason_codes':[],
                            'factor_states':[{'raw_private':'never publish'}], 'input_fingerprint':'private',
                            'origin':{'date':'2026-08-28','original_record':{'legacy_private':'never publish'}}}]}
        report['snapshot_fingerprint']=canonical_fingerprint(report)
        before=copy.deepcopy(report); public=project_report(report)
        self.assertEqual(report,before)
        self.assertEqual(public['reviews'][0]['total'],42.125)
        self.assertEqual(public['ranked_symbols'],['AAA'])
        self.assertNotIn('never publish',str(public))
        report['reviews'][0]['score']['total_score']=99
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            project_report(report)
