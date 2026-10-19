"""Task 033 synthetic execution and deterministic bank checks (local data only)."""
import importlib.util
from pathlib import Path
import unittest
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'work/v3w/standard_v1.py').exists():
    raise unittest.SkipTest('Local training helpers required; see tasks/033-daily-trainer.md')
spec = importlib.util.spec_from_file_location('daily_trainer', ROOT/'work/v3w/daily_trainer.py')
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)


def bars(n=65):
    return {'date':[(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(n)],
            'open':[101.]*n,'high':[105.]*n,'low':[99.]*n,'close':[102.]*n}


class Execution(unittest.TestCase):
    def test_gap_fill_and_planned_target(self):
        s=bars();s['open'][1]=95;s['low'][1]=94;s['high'][1]=130
        r=D.execute(s,0,100,90,130)
        self.assertEqual((r['entry'],r['exit'],r['days_held']),(95,130,1))
        self.assertAlmostEqual(r['net_R'],(130-95-.001*(130+95))/5)

    def test_stop_before_fill_and_target_before_fill(self):
        s=bars();s['open'][1]=90
        self.assertEqual(D.execute(s,0,100,90,130)['status'],'cancelled')
        s=bars();s['low'][1]=101;s['high'][1]=131
        self.assertEqual(D.execute(s,0,100,90,130)['why'],'target before the fill')

    def test_same_day_stop_wins(self):
        s=bars();s['low'][1]=89;s['high'][1]=131
        r=D.execute(s,0,100,90,130)
        self.assertEqual((r['status'],r['exit']),('loss',90))

    def test_later_gap_stop(self):
        s=bars();s['open'][2]=85;s['low'][2]=84
        r=D.execute(s,0,100,90,130)
        self.assertEqual((r['exit'],r['days_held']),(85,2))

    def test_time_day60_includes_fill(self):
        r=D.execute(bars(),0,100,90,130)
        self.assertEqual((r['status'],r['exit_day'],r['days_held'],r['exit']),('time',60,60,102))
        self.assertEqual(D.execute(bars(60),0,100,90,130)['status'],'open')

    def test_order_expiry_last_bar(self):
        s=bars(11);s['low']=[101.]*11
        self.assertEqual(D.execute(s,0,100,90,130)['status'],'cancelled')
        s=bars(10);s['low']=[101.]*10
        self.assertEqual(D.execute(s,0,100,90,130)['status'],'waiting')

    def test_second_touch(self):
        line={'pushes':[0,1,2],'line':lambda _:100}
        for v,expected in [(99.49,False),(99.5,True),(100,True),(108,True),(108.01,False)]:
            self.assertEqual(D.middle_touches([{}, {'high':v}],line),expected)

    def test_stock_uniqueness_seed_and_fallback(self):
        candidates=[dict(dataset='test',symbol=f'S{i:03}',signal_date=f'2020-01-{j:02}',group=g)
                    for i in range(130) for j in [1,2] for g in ['new','historical']]
        a=D.sample_bank(candidates)
        self.assertEqual(a,D.sample_bank(list(reversed(candidates))))
        self.assertEqual(len(a),100);self.assertEqual(len({r['symbol'] for r in a}),100)
        self.assertEqual(sum(r['group']=='new' for r in a),30)
        few=[r for r in candidates if r['group']=='historical' or int(r['symbol'][1:])<5]
        self.assertEqual(sum(r['group']=='new' for r in D.sample_bank(few)),5)

    def test_real_exclusion_mapping(self):
        excluded,mapped=D.exclusions()
        self.assertGreater(len(excluded),300)
        self.assertTrue(all((r['symbol'],D.iso_week(r['day'])) in excluded for r in mapped))
        self.assertEqual(D.iso_week('2021-01-01'),'2020-W53')


    def test_generated_bank_contract(self):
        import json, re
        key=ROOT/'work/v3w/daily1-keys.json'
        if not key.exists():self.skipTest('Generate local bank first')
        data=json.loads(key.read_text())
        page=(ROOT/'work/site-v2/daily-trainer-1.html').read_text()
        payload=json.loads(re.search(r'const BANK=(.*?);</script>',page).group(1))
        self.assertEqual(payload['keys_sha256'],D.sha(key))
        self.assertEqual(data['selected_groups'],{'historical':70,'new':30})
        self.assertEqual(len({c['symbol'] for c in data['cases']}),100)
        excluded,_=D.exclusions()
        for k,c in zip(data['cases'],payload['cases']):
            self.assertNotIn((k['symbol'],D.iso_week(k['signal_date'])),excluded)
            self.assertEqual(k['signal_date'],k['chart_last_date'])
            self.assertGreaterEqual(k['chart_first_date'],'2005-01-01')
            b=c['bars'];t=len(b)-1;a,m,z=c['pushes']
            self.assertAlmostEqual(b[-1][3],100)
            self.assertLessEqual(z,t-5)
            line=b[a][1]+(b[z][1]-b[a][1])*(m-a)/(z-a)
            self.assertTrue(.995*line<=b[m][1]<=1.08*line)
            self.assertGreater(b[t][4]-b[t][5],0)
            self.assertTrue(all(b[j][4]-b[j][5]<0 for j in range(t-4,t)))
            self.assertLess(b[t][4],0)
            plan=k['plan'];r=k['trade']
            self.assertAlmostEqual(plan['target'],plan['limit']+3*(plan['limit']-plan['stop']))
            self.assertGreaterEqual((plan['room_t1']-plan['limit'])/(plan['limit']-plan['stop']),1.5)
            self.assertTrue(1<=r['fill_day']-k['day']<=10)
            self.assertTrue(1<=r['days_held']<=60)
            self.assertAlmostEqual(k['net_R'],(r['exit']-r['entry']-.001*(r['exit']+r['entry']))/(r['entry']-plan['stop']))
        for name,h in data['frozen_source_sha256'].items():self.assertEqual(D.sha(ROOT/name),h)

if __name__=='__main__':unittest.main()
