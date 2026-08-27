import copy,json,unittest
from datetime import date,timedelta

from services.scanner.signal_history import RESET_SESSIONS,build

def inputs(day="2026-08-26",symbols=("PG",),rare=()):
 rows=[{"symbol":s,"ranking_score":70,"combined_score":10,"confluence_label":"机会","ranking_direction":"buy","rank_reason":"existing rank"} for s in symbols]
 tracker={"as_of":day,"macd_buy_top10":rows}
 radar={"as_of":day,"signals":[{"symbol":s} for s in rare]}
 factors={"as_of":day,"registry_version":"1.0","symbols":[{"symbol":s,"scoring":{"official_score":0,"experimental_observational_score":3,"score_contributions":[]},"factors":[{"factor_id":"risk.test","available":True,"hit":False,"recent_hit":False,"score_role":"display_only"}]} for s in set(symbols)|set(rare)]}
 industry={"as_of":day,"membership_version":"themes-v1","themes":[{"theme_id":"staples","name":"Staples","state":"Neutral","relative_20d":.01,"relative_60d":.02,"breadth_above_sma50":.6,"breadth_change_10d":0}],"ticker_context":{s:[{"theme_id":"staples"}] for s in set(symbols)|set(rare)}}
 return tracker,radar,factors,industry,{"as_of":day,"market_temperature":{"state":"normal"}}

def rows_through(days):
 return [{"date":(date(2026,8,26)+timedelta(days=i)).isoformat(),"open":100+i,"high":102+i,"low":98+i,"close":101+i} for i in range(days)]

class SignalHistoryTests(unittest.TestCase):
 def make(self,previous=None,day="2026-08-26",symbols=("PG",),rare=(),rows=1):
  return build(previous or {},*inputs(day,symbols,rare),day,loader=lambda _:rows_through(rows))

 def test_new_signal_deduplicates_sources_and_repeated_day(self):
  first=self.make(rare=("PG",));self.assertEqual(len(first["cases"]),1);self.assertEqual(first["cases"][0]["source_systems"],["multi_factor_radar","technical_tracker"])
  second=self.make(first,"2026-08-27",rare=("PG",),rows=2);self.assertEqual(len(second["cases"]),1);self.assertEqual(second["cases"][0]["days_active"],2)

 def test_dropped_case_survives_and_reentry_after_objective_reset_is_new(self):
  history=self.make()
  for i in range(1,RESET_SESSIONS+1):history=self.make(history,f"2026-08-{26+i:02d}",symbols=(),rows=i+1)
  self.assertEqual(len(history["cases"]),1);self.assertEqual(history["cases"][0]["latest_current_status"],"dropped")
  history=self.make(history,"2026-09-01",rows=7);self.assertEqual(len(history["cases"]),2)

 def test_original_evidence_and_industry_are_immutable(self):
  first=self.make();original=copy.deepcopy(first["cases"][0]["signal_time_snapshot"])
  second=self.make(first,"2026-08-27",rows=2)
  self.assertEqual(second["cases"][0]["signal_time_snapshot"],original)

 def test_tampered_original_snapshot_fails_closed(self):
  history=self.make();history["cases"][0]["signal_time_snapshot"]["technical"]["technical_score"]=999
  with self.assertRaisesRegex(ValueError,"Immutable"):self.make(history,"2026-08-27",rows=2)

 def test_forward_horizons_and_excursions_use_only_elapsed_rows(self):
  history=self.make(rows=1);history=self.make(history,"2026-08-27",rows=2);case=history["cases"][0]
  self.assertIsNotNone(case["forward"]["returns"]["1"]);self.assertIsNone(case["forward"]["returns"]["5"]);self.assertIsNone(case["forward"]["returns"]["20"])
  self.assertEqual(case["forward"]["elapsed_sessions"],1);self.assertAlmostEqual(case["forward"]["mfe"],103/101-1)

 def test_twenty_day_return_requires_twenty_completed_entry_sessions(self):
  first=self.make(rows=1);pending=self.make(first,"2026-09-14",rows=20)["cases"][0];ready=self.make(first,"2026-09-15",rows=21)["cases"][0]
  self.assertIsNone(pending["forward"]["returns"]["20"]);self.assertIsNotNone(ready["forward"]["returns"]["20"])

 def test_historical_cache_future_rows_are_cut_at_as_of(self):
  future=rows_through(21);future.append({"date":"2027-01-01","open":1,"high":9999,"low":0.01,"close":9999})
  history=build({},*inputs(),"2026-08-26",loader=lambda _:future)
  self.assertIsNone(history["cases"][0]["entry"]["date"]);self.assertIsNone(history["cases"][0]["forward"]["mfe"])

 def test_eodhd_month_day_year_rows_are_normalized_before_horizon_logic(self):
  first=self.make(rows=1);rows=[{"date":"08/26/2026","open":100,"high":101,"low":99,"close":100},{"date":"08/27/2026","open":101,"high":103,"low":100,"close":102}]
  history=build(first,*inputs("2026-08-27"),"2026-08-27",loader=lambda _:rows)
  self.assertEqual(history["cases"][0]["entry"]["date"],"2026-08-27");self.assertIsNotNone(history["cases"][0]["forward"]["returns"]["1"])

 def test_losers_pending_versions_and_deterministic_content_are_preserved(self):
  down=[{"date":"2026-08-26","open":100,"high":101,"low":99,"close":100},{"date":"2026-08-27","open":100,"high":100,"low":90,"close":91}]
  a=self.make(rows=1);b=self.make(rows=1);self.assertEqual(a["content_hash"],b["content_hash"]);self.assertEqual(a["cases"][0]["product_version"],"SV-PRODUCT-V1")
  first=self.make(rows=1);loss=build(first,*inputs("2026-08-27"),"2026-08-27",loader=lambda _:down);self.assertLess(loss["cases"][0]["forward"]["returns"]["1"],0);self.assertEqual(len(loss["cases"]),1)

 def test_unavailable_outcome_keeps_case(self):
  history=self.make();updated=build(history,*inputs("2026-08-27",symbols=()),"2026-08-27",loader=lambda _:(_ for _ in ()).throw(RuntimeError("delisted")))
  self.assertEqual(len(updated["cases"]),1);self.assertEqual(updated["cases"][0]["forward"]["data_status"],"unavailable")

if __name__=="__main__":unittest.main()
