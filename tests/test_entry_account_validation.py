import copy
import unittest
from research.backtest.entry_account_validation import order_inputs,validate_inputs,frozen_ranks,validate_comparison
from research.backtest.run_store import POLICY

CONFIG={'initial_cash':100000,'allocation_fraction':.1,'max_positions':10,'cost_rate':.001,'fractional_shares':False}


def candidate(eid,day,tf='daily',rank=1):
    return {'event_id':eid,'symbol':eid,'signal_date':day,'selection':{'opportunity_timeframe':tf,'rank':rank,'technical_score':30,'execution_policy_version':POLICY,'support_plan':{'level':90,'source':'test'}}}


def opportunity(e,trigger=None,status='filled'):
    return {'episode_id':e['event_id'],'wait_end':'2026-12-31','source_timeline':[],
            'methods':{'support':{'trigger_date':trigger,'status':status}}}

class InputTests(unittest.TestCase):
    def setUp(self):
        self.es=[candidate('M','2025-01-02','monthly_completed'),candidate('W','2025-01-03','weekly_completed')]
        self.ops=[opportunity(self.es[0],'2025-01-20')]
    def test_only_monthly_date_changes_and_support_stays_frozen(self):
        a,b,states=order_inputs(self.es,self.ops);validate_inputs(self.es,a,b,states)
        self.assertEqual(a[0]['selection'],b[0]['selection']);self.assertEqual(a[1],b[1])
    def test_changed_rank_support_score_or_daily_date_rejected(self):
        for field in ['rank','technical_score','support_plan']:
            a,b,st=order_inputs(self.es,self.ops);b[0]['selection'][field]='changed'
            with self.assertRaisesRegex(ValueError,'more_than_entry'):validate_inputs(self.es,a,b,st)
        a,b,st=order_inputs(self.es,self.ops);b[1]['signal_date']='2025-01-04'
        with self.assertRaisesRegex(ValueError,'non_monthly'):validate_inputs(self.es,a,b,st)
    def test_expired_and_invalidated_never_create_forced_order(self):
        for saved,state in [('waiting_censored','EXPIRED'),('invalidated','INVALIDATED')]:
            a,b,st=order_inputs(self.es,[opportunity(self.es[0],None,saved)]);validate_inputs(self.es,a,b,st)
            self.assertEqual(len(b),1);self.assertEqual(st['M']['state'],state)
    def test_full_account_variable_mismatch_rejected(self):
        a,b,st=order_inputs(self.es,self.ops)
        d={'price_manifest':{'files':{'M':{},'W':{},'SPY':{}}},'candidates':self.es,'orders':{'A':a,'B':b},'monthly_states':st,'engine_identity':{'A':{},'B':{}},'scenarios':{'A':CONFIG,'B':{**CONFIG,'cost_rate':0}}}
        with self.assertRaisesRegex(ValueError,'config_mismatch'):validate_comparison(d,{})
    def test_original_comparator_and_frozen_same_day_ranks(self):
        es=[{'episode_id':s,'symbol':s,'signal_date':'2020-01-01','score':v,'timeframe_scores':{'monthly_completed':10,'weekly_completed':20}} for s,v in [('A',10),('B',20)]]
        self.assertEqual(frozen_ranks(es),{'B':1,'A':2})

class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import vectorbt
            import quantstats
            import pandas
        except ImportError:raise unittest.SkipTest('account dependencies required')
        cls.pd=pandas
    def fixture(self):
        days=self.pd.bdate_range('2025-01-02',periods=70).strftime('%Y-%m-%d').tolist()
        rows=[dict(date=d,open=100.,high=101.,low=99.,close=100.,volume=100000) for d in days]
        return days,rows
    def test_holding_clock_starts_at_actual_fill(self):
        from research.backtest.account_runner import account
        ds,rs=self.fixture();e=candidate('M',ds[0],'monthly_completed');a,b,st=order_inputs([e],[opportunity(e,ds[10])])
        aa=account(a,{'M':rs},ds,CONFIG)[2][0];bb=account(b,{'M':rs},ds,CONFIG)[2][0]
        self.assertEqual(aa['execution']['holding_sessions'],40);self.assertEqual(bb['execution']['holding_sessions'],40)
        self.assertEqual(bb['entry_date'],ds[11]);self.assertEqual(bb['execution']['exit_date'],ds[50])
        self.assertEqual(bb['execution']['exit_reason'],'time_40d')
    def test_waiting_changes_cash_and_allows_later_weekly_fill(self):
        from research.backtest.account_runner import account
        ds,rs=self.fixture();es=[candidate('M',ds[0],'monthly_completed')]+[candidate('D'+str(i),ds[0],rank=i+2) for i in range(8)]+[candidate('W',ds[2],'weekly_completed')]
        a,b,st=order_inputs(es,[opportunity(es[0],ds[10])]);rows={e['symbol']:rs for e in es}
        ta={t['event_id']:t for t in account(a,rows,ds,CONFIG,with_ledger=True)[2]}
        tb={t['event_id']:t for t in account(b,rows,ds,CONFIG,with_ledger=True)[2]}
        self.assertEqual(ta['W']['reason'],'cash_or_whole_share_insufficient');self.assertEqual(tb['W']['status'],'closed')
        self.assertEqual(tb['M']['reason'],'cash_or_whole_share_insufficient')
    def test_mixed_execution_support_and_account_bindings_fail(self):
        from research.backtest.account_runner import account,attach_signal_audit
        from research.backtest.price_identity import freeze_manifest,bind,digest
        ds,rs=self.fixture();es=[candidate('M',ds[0],'monthly_completed')]
        a,b,st=order_inputs(es,[opportunity(es[0],ds[0])])
        eq,ret,trades,ledger=account(a,{'M':rs},ds,CONFIG,with_ledger=True);attach_signal_audit(trades,a)
        book={'trades':trades,'ledger':ledger,'daily_account':[{'date':d,'equity':float(v),'return':float(r)} for d,v,r in zip(ds,eq,ret)]}
        manifest=freeze_manifest({'M':{'raw_sha256':'synthetic'},'SPY':{'raw_sha256':'synthetic'}},source={'synthetic':True})
        contract={'manifest':manifest,**{k:bind(v,manifest,symbols=['M'],verified=True) for k,v in {
            'setup':es,'signal':a,'support':{'M':es[0]['selection']['support_plan']},'execution':trades,'account':{'book_sha256':digest(book)}}.items()}}
        data={'price_manifest':manifest,'candidates':es,'orders':{'A':a,'B':b},'monthly_states':st,'engine_identity':{'A':{},'B':{}},'scenarios':{'A':CONFIG,'B':CONFIG},'contracts':{'A':contract,'B':copy.deepcopy(contract)}}
        self.assertTrue(validate_comparison(data,{'A':book,'B':book}))
        for role in ['signal','support','execution','account']:
            bad=copy.deepcopy(data);bad['contracts']['B'][role]['price_version']='other'
            with self.assertRaises(ValueError):validate_comparison(bad,{'A':book,'B':book})
        bad=copy.deepcopy(book);bad['ledger']['days'][0]['ending_cash']+=1
        with self.assertRaisesRegex(ValueError,'account_source'):validate_comparison(data,{'A':book,'B':bad})
    def test_missing_held_prices_fail_not_forward_fill(self):
        from research.backtest.account_runner import account
        ds,rs=self.fixture();del rs[3]
        with self.assertRaisesRegex(ValueError,'held_asset_session_missing'):account([candidate('M',ds[0])],{'M':rs},ds,CONFIG)

if __name__=='__main__':unittest.main()
