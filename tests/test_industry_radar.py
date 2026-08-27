import hashlib,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path

from services.scanner.industry_radar import calculate,classify_state,member_metrics,rows_as_of,run,select_snapshot
from services.scanner.industry_membership import analyze_overlap,configured_themes,parse_first_trust,parse_global_x,parse_invesco,parse_ishares,parse_state_street,parse_vaneck

def series(rate=0.001,count=90,start="2026-01-01"):
 day=date.fromisoformat(start);price=100;rows=[]
 for i in range(count):
  price*=1+rate;rows.append({"date":(day+timedelta(days=i)).isoformat(),"close":price})
 return rows

def theme(theme_id="one",members=None,effective="2026-01-01"):
 return {"theme_id":theme_id,"name":theme_id.title(),"source_type":"official_etf_holdings","source":"ETF","source_url":"https://example.test","source_date":effective,"effective_from":effective,"members":members or ["A","B","C","D","E"]}

class IndustryRadarTests(unittest.TestCase):
 def test_provider_adapters_parse_ticker_columns_without_guessing(self):
  generic="Name,Ticker,Weight\nNvidia,NVDA,10\nForeign,BMN AU,2\nCash,USD,1\n"
  self.assertEqual(parse_ishares(generic),["NVDA","BMN AU"])
  self.assertEqual(parse_first_trust(generic),["NVDA","BMN AU"])
  self.assertEqual(parse_invesco("Name,Holding Ticker\nNvidia,NVDA\n"),["NVDA"])
  self.assertEqual(parse_vaneck(generic),["NVDA","BMN AU"])
  self.assertEqual(parse_state_street(generic.encode()),["NVDA","BMN AU"])

 def test_overlap_analysis_flags_near_duplicates(self):
  rows=[theme("clean",["A","B","C","D"]),theme("solar",["A","B","C"]),theme("water",["X","Y"])]
  pairs=analyze_overlap(rows)
  pair=next(x for x in pairs if {x["theme_a"],x["theme_b"]}=={"clean","solar"})
  self.assertEqual(pair["shared_count"],3);self.assertEqual(pair["overlap_pct"],1);self.assertEqual(pair["review"],"near_duplicate")

 def test_foreign_market_identifier_is_preserved_for_unavailable_audit(self):
  csv_text="Fund\n% of Net Assets,Ticker,Name\n1.0,BMN AU,Bannerman\n1.0,NVDA,Nvidia\n"
  self.assertEqual(parse_global_x(csv_text),["BMN AU","NVDA"])

 def test_theme_source_configuration_is_data_driven(self):
  with tempfile.TemporaryDirectory() as folder:
   registry=Path(folder,"registry.json");registry.write_text(json.dumps({"themes":[{"theme_id":"configured","name":"Configured","membership_source":{"provider":"global_x","fund":"TEST"}},{"theme_id":"manual","name":"Manual","status":"manual_curated_required"}]}))
   self.assertEqual([x["theme_id"] for x in configured_themes(registry)],["configured"])
 def test_no_price_row_after_as_of(self):
  rows=[{"date":"2026-01-01","close":1},{"date":"2026-01-03","close":99}]
  self.assertEqual([x["date"] for x in rows_as_of(rows,"2026-01-02")],["2026-01-01"])

 def test_future_membership_cannot_leak_backward(self):
  with tempfile.TemporaryDirectory() as folder:
   Path(folder,"2026-02-01.json").write_text(json.dumps({"effective_from":"2026-02-01"}))
   self.assertIsNone(select_snapshot("2026-01-31",folder))

 def test_newest_eligible_membership_is_selected(self):
  with tempfile.TemporaryDirectory() as folder:
   for day in ("2026-01-01","2026-02-01","2026-03-01"):Path(folder,f"{day}.json").write_text(json.dumps({"effective_from":day,"version":day}))
   self.assertEqual(select_snapshot("2026-02-10",folder)["version"],"2026-02-01")

 def test_higher_snapshot_revision_wins_on_same_effective_date(self):
  with tempfile.TemporaryDirectory() as folder:
   Path(folder,"base.json").write_text(json.dumps({"effective_from":"2026-02-01","version":"v1"}))
   Path(folder,"corrected.json").write_text(json.dumps({"effective_from":"2026-02-01","snapshot_revision":2,"version":"v2"}))
   self.assertEqual(select_snapshot("2026-02-01",folder)["version"],"v2")

 def test_theme_basket_is_equal_weighted(self):
  spy=series(0);data={"A":series(.01),"B":series(0),"C":series(0),"D":series(0),"E":series(0)}
  themes,_=calculate({"themes":[theme()]},data,spy,"2026-03-31")
  expected=(data["A"][-1]["close"]/data["A"][-21]["close"]-1)/5
  self.assertAlmostEqual(themes[0]["return_20d"],expected)

 def test_breadth_calculation(self):
  spy=series(0);data={x:series(.01 if x in "ABC" else -.01) for x in "ABCDE"}
  themes,_=calculate({"themes":[theme()]},data,spy,"2026-03-31")
  self.assertAlmostEqual(themes[0]["breadth_above_sma50"],.6)
  self.assertAlmostEqual(themes[0]["breadth_positive_20d"],.6)

 def test_pullback_precedes_leadership(self):
  item={"valid_member_count":10,"strength_percentile":90,"breadth_above_sma50":.8,"relative_5d":-.01,"breadth_change_10d":0}
  self.assertEqual(classify_state(item),"Pullback Watch")

 def test_missing_constituents_do_not_crash(self):
  spy=series(0);data={x:series(.001) for x in "ABCDE"};data["Z"]=[]
  themes,_=calculate({"themes":[theme(members=["A","B","C","D","E","Z"])]},data,spy,"2026-03-31")
  self.assertEqual(themes[0]["valid_member_count"],5)

 def test_insufficient_theme_is_safe(self):
  themes,_=calculate({"themes":[theme(members=["A","B"])]},{"A":series(),"B":series()},series(0),"2026-03-31")
  self.assertEqual(themes[0]["state"],"Unavailable");self.assertIsNone(themes[0]["relative_20d"])

 def test_ticker_can_belong_to_multiple_themes(self):
  snapshot={"themes":[theme("one"),theme("two")]};data={x:series(.001) for x in "ABCDE"}
  _,lookup=calculate(snapshot,data,series(0),"2026-03-31")
  self.assertEqual({x["theme_id"] for x in lookup["A"]},{"one","two"})

 def test_radar_does_not_change_tracker_output(self):
  tracker=Path(__file__).parents[1]/"public/resonance-tracker.json";before=hashlib.sha256(tracker.read_bytes()).hexdigest()
  with tempfile.TemporaryDirectory() as folder:
   snapshot={"version":"v1","effective_from":"2026-01-01","themes":[theme()]};Path(folder,"v1.json").write_text(json.dumps(snapshot))
   run(Path(folder,"radar.json"),"2026-03-31",folder,loader=lambda _:series())
  self.assertEqual(hashlib.sha256(tracker.read_bytes()).hexdigest(),before)

 def test_price_audit_records_failed_tickers_without_error_text(self):
  with tempfile.TemporaryDirectory() as folder:
   snapshot={"version":"v1","effective_from":"2026-01-01","themes":[theme()]};Path(folder,"v1.json").write_text(json.dumps(snapshot))
   def loader(symbol):
    if symbol=="B":raise RuntimeError("secret-bearing provider URL")
    return [] if symbol=="C" else series()
   report=run(Path(folder,"radar.json"),"2026-03-31",folder,loader=loader)
   self.assertEqual(report["price_data_audit"]["unavailable_tickers"],["B","C"])
   self.assertNotIn("secret-bearing",json.dumps(report))

 def test_member_metric_is_point_in_time(self):
  rows=series();future={"date":"2027-01-01","close":1_000_000};rows.append(future)
  result=member_metrics(rows,series(0),"2026-03-31")
  self.assertLess(result["return_20d"],1)

if __name__=="__main__":unittest.main()
