import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace

from services.scanner.open_source_industry import classification_by_ticker,openbb_etf_holdings,openbb_nport_disclosure,parse_finance_database_csv,select_finance_database_snapshot,snapshot_finance_database

CSV="symbol,name,sector,industry_group,industry,exchange,market,market_cap,delisted\nAAA,Alpha,Industrials,Capital Goods,Robotics,NMS,NASDAQ,Small Cap,False\nBBB,Beta,Energy,Energy,Oil,NYQ,NYSE,Mid Cap,False\n"

class Frame:
 def reset_index(self):return self
 def to_dict(self,orient):return [{"symbol":"AAA"}]
class Result:
 def to_df(self):return Frame()
class Endpoint:
 def __init__(self):self.calls=[]
 def __call__(self,**kwargs):self.calls.append(kwargs);return Result()

class OpenSourceIndustryTests(unittest.TestCase):
 def test_finance_database_parser_keeps_three_level_taxonomy(self):
  rows=parse_finance_database_csv(CSV,{"AAA"})
  self.assertEqual(rows[0]["sector"],"Industrials");self.assertEqual(rows[0]["industry_group"],"Capital Goods");self.assertEqual(rows[0]["industry"],"Robotics")

 def test_snapshot_is_versioned_and_never_claims_historical_truth(self):
  with tempfile.TemporaryDirectory() as folder:
   out=Path(folder,"snapshot.json");payload=snapshot_finance_database(["AAA","MISSING"],"2026-08-27",out,downloader=lambda _:CSV)
   self.assertFalse(payload["historical_backfill_allowed"]);self.assertEqual(payload["matched_symbols"],1);self.assertEqual(payload["unmatched_symbols"],["MISSING"])
   with self.assertRaises(FileExistsError):snapshot_finance_database(["AAA"],"2026-08-27",out,downloader=lambda _:CSV)

 def test_snapshot_selection_never_leaks_current_classification_backward(self):
  with tempfile.TemporaryDirectory() as folder:
   snapshot_finance_database(["AAA"],"2026-08-27",Path(folder,"finance-database-2026-08-27.json"),downloader=lambda _:CSV)
   self.assertIsNone(select_finance_database_snapshot("2026-08-26",folder))
   chosen=select_finance_database_snapshot("2026-08-27",folder)
   self.assertEqual(classification_by_ticker(chosen)["AAA"]["industry"],"Robotics")

 def test_openbb_is_an_isolated_adapter_not_copied_source(self):
  holdings=Endpoint();nport=Endpoint();client=SimpleNamespace(etf=SimpleNamespace(holdings=holdings,nport_disclosure=nport))
  self.assertEqual(openbb_etf_holdings("aaa",client=client),[{"symbol":"AAA"}])
  openbb_nport_disclosure("botz","2025-01-01","2025-12-31",client)
  self.assertEqual(nport.calls[0],{"symbol":"BOTZ","provider":"sec","start_date":"2025-01-01","end_date":"2025-12-31"})

if __name__=="__main__":unittest.main()
