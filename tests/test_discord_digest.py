import unittest
from services.scanner.discord_daily_digest import build_payload,notification_keys,validate_inputs

class DiscordDigestTests(unittest.TestCase):
 def fixtures(self):
  status={"status":"up_to_date","source_latest_complete_date":"2026-08-24","tracker_as_of":"2026-08-24","radar_as_of":"2026-08-24","data_dates_match":True,"future_data_used":False}
  item={"symbol":"ABC","price":10,"macd_rank_score":8};tracker={"as_of":"2026-08-24","macd_buy_top10":[item],"macd_sell_top10":[],"consistency_audit":{"ranking_digest":"abc123"}}
  signal={"symbol":"ABC","date":"2026-08-24","price":10,"score":5,"total_score":5,"components":["EMA支撑"],"factor_ids":["support.ema_proximity"],"risks":["研究观察"]};radar={"as_of":"2026-08-24","scan":{"future_data_used":False},"signals":[signal]}
  return status,tracker,radar
 def test_payload_prioritizes_rare_before_macd(self):
  _,tracker,radar=self.fixtures();payload,rare=build_payload(tracker,radar)
  self.assertEqual(rare[0]["symbol"],"ABC");self.assertTrue(payload["embeds"][0]["title"].startswith("稀有机会"));self.assertTrue(payload["embeds"][-1]["title"].startswith("MACD 日榜"))
  self.assertIn("不是自动买入",payload["embeds"][0]["footer"]["text"])
 def test_five_points_meets_rare_threshold(self):
  _,tracker,radar=self.fixtures();_,rare=build_payload(tracker,radar,minimum_rare_score=5);self.assertEqual(len(rare),1)
 def test_notification_keys_are_stable_for_dedup(self):
  _,tracker,radar=self.fixtures();_,rare=build_payload(tracker,radar);self.assertEqual(notification_keys(tracker,rare),notification_keys(tracker,rare))
 def test_mismatched_dates_fail_closed(self):
  status,tracker,radar=self.fixtures();radar["as_of"]="2026-08-21"
  with self.assertRaisesRegex(RuntimeError,"not synchronized"):validate_inputs(status,tracker,radar)

if __name__=="__main__":unittest.main()
