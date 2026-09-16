import unittest
from research.backtest.observation_continuation import paired, state, stats, interval


class ContinuationTests(unittest.TestCase):
    def event(self):
        return {'episode_id':'x','symbol':'X','signal_date':'2010-01-01','outcomes':{
            '3m':{'status':'complete','return':.5,'spy_return':.1,'target_date':'2010-04-01'},
            '6m':{'status':'complete','return':.2,'spy_return':.21,'target_date':'2010-07-01'}}}

    def test_rebases_price_and_benchmark_instead_of_subtracting_returns(self):
        r=paired(self.event(),'3m','6m')
        self.assertAlmostEqual(r['return'],-.2)
        self.assertAlmostEqual(r['excess'],-.3)

    def test_missing_and_zero_price_are_not_zero_return(self):
        e=self.event();e['outcomes']['6m']['status']='missing_prices'
        self.assertIsNone(paired(e,'3m','6m'))
        e=self.event();e['outcomes']['3m']['return']=-1
        self.assertIsNone(paired(e,'3m','6m'))

    def test_checkpoint_state_never_uses_later_gain(self):
        e=self.event();a=paired(e,'3m','6m')
        e['outcomes']['6m']['return']=10
        self.assertEqual(a['state'],paired(e,'3m','6m')['state'])
        self.assertEqual([state(v) for v in [-.051,-.05,.05,.051]],['下跌','横盘','横盘','上涨'])

    def test_sparse_clusters_refuse_interval(self):
        r=paired(self.event(),'3m','6m')
        self.assertIsNone(interval([r]*100,'symbol'))
        self.assertIsNone(interval([r]*100,'time'))
        self.assertEqual(stats([]),{'n':0,'symbols':0})


if __name__=='__main__':
    unittest.main()
