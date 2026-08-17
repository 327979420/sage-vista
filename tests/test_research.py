import unittest
from services.scanner.research_pipeline import classify_factor,factor_values,rank,spearman
class ResearchTests(unittest.TestCase):
 def test_rank_ties(self):self.assertEqual(rank([2,1,2]),[2.5,1,2.5])
 def test_spearman(self):self.assertAlmostEqual(spearman([1,2,3],[10,20,30]),1)
 def test_factor_uses_past_only(self):
  rows=[{"close":100+i*.1,"volume":1000000,"open":0,"high":0,"low":0,"date":str(i)} for i in range(300)]
  a=factor_values(rows,270);rows[290]["close"]=9999;b=factor_values(rows,270);self.assertEqual(a,b)
 def test_factor_classification_requires_validation(self):
  good=lambda ic,pct:{"factor":"x","horizon":60,"mean_ic":ic,"ic_positive_pct":pct}
  self.assertEqual(classify_factor([good(.04,60)],[good(.03,58)],[],"x"),"promising")
  self.assertEqual(classify_factor([good(.04,60)],[good(-.03,40)],[],"x"),"unstable")
if __name__=="__main__":unittest.main()
