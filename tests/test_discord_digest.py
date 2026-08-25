import unittest
from services.scanner.discord_daily_digest import build_payload,collect_alerts,notification_keys,pending_plan,validate_inputs

class DiscordDigestTests(unittest.TestCase):
 def fixtures(self):
  status={"status":"up_to_date","source_latest_complete_date":"2026-08-24","tracker_as_of":"2026-08-24","radar_as_of":"2026-08-24","data_dates_match":True,"future_data_used":False}
  item={"symbol":"ABC","price":10,"macd_rank_score":8};tracker={"as_of":"2026-08-24","macd_top10":[item],"macd_buy_top10":[item],"macd_sell_top10":[],"consistency_audit":{"ranking_digest":"abc123"}}
  signal={"symbol":"ABC","date":"2026-08-24","price":10,"score":5,"total_score":5,"components":["EMA支撑"],"factor_ids":["support.ema_proximity"],"risks":["研究观察"]};radar={"as_of":"2026-08-24","scan":{"future_data_used":False},"signals":[signal]}
  return status,tracker,radar
 def test_payload_keeps_alerts_and_adds_two_minimal_rankings(self):
  _,tracker,radar=self.fixtures();payload,alerts=build_payload(tracker,radar)
  self.assertEqual(alerts[0]["symbol"],"ABC");self.assertTrue(payload["embeds"][0]["title"].startswith("Confirmed"))
  self.assertEqual(payload["embeds"][-2]["title"],"MACD Ranking — 2026-08-24")
  self.assertEqual(payload["embeds"][-1]["title"],"Multi-Factor Ranking — 2026-08-24")
  self.assertEqual(payload["embeds"][-2]["description"],"1. ABC")
  self.assertEqual(payload["embeds"][-1]["description"],"1. ABC")
  self.assertNotIn("$",payload["embeds"][-2]["description"]);self.assertNotIn("分",payload["embeds"][-1]["description"])
  self.assertIn("不是自动买入",payload["embeds"][0]["footer"]["text"])
 def test_five_points_meets_rare_threshold(self):
  _,tracker,radar=self.fixtures();_,alerts=build_payload(tracker,radar,minimum_rare_score=5);self.assertEqual(len(alerts),1)
 def test_notification_keys_are_stable_for_dedup(self):
  _,tracker,radar=self.fixtures();_,rare=build_payload(tracker,radar);self.assertEqual(notification_keys(tracker,radar,rare),notification_keys(tracker,radar,rare))
 def test_mismatched_dates_fail_closed(self):
  status,tracker,radar=self.fixtures();radar["as_of"]="2026-08-21"
  with self.assertRaisesRegex(RuntimeError,"not synchronized"):validate_inputs(status,tracker,radar)
 def test_early_watch_to_confirmed_can_alert_twice_without_same_state_duplicates(self):
  early={"symbol":"ABC","status":"early_watch"};confirmed={"symbol":"ABC","status":"confirmed"};keys=["status:ABC:early_watch","ranking:macd:date","ranking:multi-factor:date"]
  self.assertEqual(pending_plan([early],keys,{"sent":[],"symbol_status":{}})[0],[0])
  self.assertEqual(pending_plan([early],keys,{"sent":[],"symbol_status":{"ABC":"early_watch"}})[0],[])
  self.assertEqual(pending_plan([early],keys,{"sent":[],"symbol_status":{"ABC":"confirmed"}})[0],[])
  confirmed_keys=["status:ABC:confirmed",*keys[1:]]
  self.assertEqual(pending_plan([confirmed],confirmed_keys,{"sent":[],"symbol_status":{"ABC":"early_watch"}})[0],[0])
  self.assertEqual(pending_plan([confirmed],confirmed_keys,{"sent":[],"symbol_status":{"ABC":"confirmed"}})[0],[])
 def test_rankings_deduplicate_independently_once_per_date(self):
  _,tracker,radar=self.fixtures();_,alerts=build_payload(tracker,radar);keys=notification_keys(tracker,radar,alerts)
  state={"sent":[keys[-2]],"symbol_status":{"ABC":"confirmed"}}
  alert_indices,ranking_pending=pending_plan(alerts,keys,state)
  self.assertEqual(alert_indices,[]);self.assertEqual(ranking_pending,[False,True])

if __name__=="__main__":unittest.main()
