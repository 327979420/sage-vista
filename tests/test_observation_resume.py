import unittest
from research.backtest.observation_resume import action

class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.meta={'path':'.github/workflows/opportunity-ledger-refresh.yml','event':'workflow_dispatch','head_branch':'main','head_sha':'a'*40,'status':'completed','conclusion':'success','run_attempt':2}
        self.jobs=[{'name':'observation_shards (0)','conclusion':'success'}]
        self.progress={'code':'a'*40,'complete':False,'progress_fingerprint':'changed'}
    def test_pending_same_original_run(self):
        self.assertEqual(action(self.meta,self.jobs,self.progress,{'progress_fingerprint':'old'}),'all')
        self.progress['complete']=True
        self.assertIsNone(action(self.meta,self.jobs,self.progress))
    def test_stalled_and_automatic_limit(self):
        self.assertIsNone(action(self.meta,self.jobs,self.progress,self.progress))
        self.meta['run_attempt']=12
        self.assertIsNone(action(self.meta,self.jobs,self.progress))
        self.assertEqual(action(self.meta,self.jobs,self.progress,manual=True),'all')
    def test_never_duplicate_active_or_cancelled(self):
        self.meta['status']='in_progress'
        self.assertIsNone(action(self.meta,self.jobs,self.progress))
        with self.assertRaisesRegex(ValueError,'still_active'):action(self.meta,self.jobs,manual=True)
        self.meta.update(status='completed',conclusion='cancelled')
        self.assertIsNone(action(self.meta,self.jobs,self.progress))
    def test_reject_mixed_code_and_non_observation(self):
        self.progress['code']='b'*40
        with self.assertRaisesRegex(ValueError,'identity_invalid'):action(self.meta,self.jobs,self.progress)
        self.assertIsNone(action(self.meta,[]))
        with self.assertRaisesRegex(ValueError,'not_an_original'):action(self.meta,[],manual=True)
    def test_legacy_failed_only_and_cap(self):
        self.meta['conclusion']='failure';self.jobs[0]['conclusion']='timed_out'
        self.assertEqual(action(self.meta,self.jobs),'failed')
        self.meta['run_attempt']=3
        self.assertIsNone(action(self.meta,self.jobs))
        self.assertEqual(action(self.meta,self.jobs,manual=True),'failed')
        self.jobs[0]['conclusion']='success'
        self.assertIsNone(action(self.meta,self.jobs,manual=True))
    def test_old_success_without_pending_receipt_is_finished(self):
        self.assertIsNone(action(self.meta,self.jobs))
