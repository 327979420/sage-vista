import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from research.lab import forward_judge as J, triangle_forward as F


def fixture():
    dates = []
    day = dt.date(2020, 1, 1)
    while len(dates) < 700:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += dt.timedelta(days=1)
    s = {"date": dates, "open": [100.] * 700, "high": [102.] * 700,
         "low": [97.] * 700, "close": [100.] * 700, "volume": [1e7] * 700}
    W = J.BS.periods(s, "week")
    idx = 504
    week = W["date"][J.BS.completed(W, idx, 700)]
    rec = {"id": "synthetic", "symbol": "TEST", "signal_day": dates[idx], "week": week,
           "plan": {"go": True, "level": 98., "stop": 90., "t1": 110.}, "market": {"ok": True}}
    px = {"TEST": s, **{f"T{i}": copy.deepcopy(s) for i in range(35)}}
    return px, rec


def rows(n, positive=False):
    return [{"id": str(i), "exit_date": (dt.date(2020, 1, 1) + dt.timedelta(days=i)).isoformat(), "eligible": True, "completed": True, "scored": True,
             "d": (1 if positive else -1) + .1 * (i % 2), "trade": {"net_R": .5},
             "net_twin_mean": .2, "gross_difference": .3, "check": "一致", "frozen": {"random_R": .2}}
            for i in range(n)]


class ForwardJudgeTests(unittest.TestCase):
    def test_net_hand_example(self):
        self.assertAlmostEqual(J.net_r(100, 130, 90), 2.977)

    def replay(self, px, rec):
        rules = {**J.N.POOL, "exclude": J.selection.impossible_jumps(px) | J.N.FUNDS}
        pool = [x for x in J.selection.eligible_pool(px, rec["signal_day"], rules) if x != rec["symbol"]]
        with patch.object(F, "PX", px):
            frozen = F.outcome(rec, pool)
        return J.recompute(px, [rec], [frozen], {"random_twins": 30})[0], frozen, pool

    def test_twins_equal_frozen_and_draw_order(self):
        px, rec = fixture()
        before = copy.deepcopy(px)
        row, frozen, pool = self.replay(px, rec)
        self.assertEqual(round(row["gross_twin_mean"], 4), frozen["r19"]["random_R"])
        seed = int(hashlib.sha256(rec["id"].encode()).hexdigest()[:8], 16)
        self.assertEqual([t["symbol"] for t in row["twins"]], random.Random(seed).sample(pool, 30))
        self.assertEqual(px, before)
        self.assertTrue(row["scored"])
        self.assertEqual(row["exit_date"], px[rec["symbol"]]["date"][row["trade"]["exit_day"]])

    def test_unfilled_17_still_scores_19(self):
        px, rec = fixture()
        i = px["TEST"]["date"].index(rec["signal_day"]) + 1
        px["TEST"]["low"][i] = 99
        px["TEST"]["high"][i] = 112
        row, frozen, _ = self.replay(px, rec)
        self.assertEqual(frozen["status"], "cancelled")
        self.assertNotIn("random_R", frozen["r19"])
        self.assertTrue(row["scored"])
        self.assertEqual(row["check"], "无冻结核对")
        self.assertEqual(J.score([row])["no_frozen_check"], 1)

    def test_mismatch_counted_excluded(self):
        px, rec = fixture()
        row, frozen, _ = self.replay(px, rec)
        for key in ("R", "random_R"):
            bad = copy.deepcopy(frozen)
            bad["r19"][key] += 1
            r = J.recompute(px, [rec], [bad], {})[0]
            score = J.score([r])
            self.assertEqual(r["check"], "对照不一致")
            self.assertEqual((score["completed"], score["scored"]), (1, 0))
            self.assertIsNone(score["mean_d"])

    def test_pause_strictly_over_ten_percent(self):
        rs = rows(30)
        for r in rs[:3]:
            r["scored"] = False
        self.assertTrue(J.score(rs)["alarm1"])
        rs[3]["scored"] = False
        out = J.score(rs)
        self.assertEqual(out["verdict"], "暂停判断（对照不足）")
        self.assertFalse(out["alarm1"])
        self.assertEqual(out["completed"], 30)

    def test_empty(self):
        out = J.score([])
        self.assertEqual((out["completed"], out["to_go"]), (0, 30))
        self.assertIsNone(out["t"])
        self.assertIn("已结束 0 笔", J.markdown(out))
        json.dumps(out, allow_nan=False)

    def test_29_30_boundary(self):
        self.assertFalse(J.score(rows(29))["alarm1"])
        self.assertTrue(J.score(rows(30))["alarm1"])
        self.assertEqual(J.score(rows(29))["to_go"], 1)
        self.assertEqual(J.score(rows(30))["next_checkpoint"], 60)

    def test_alarm_only_checkpoints(self):
        for n in (31, 59, 61, 99, 101, 199):
            self.assertEqual(J.score(rows(n))["checkpoints"], J.score(rows(n-1))["checkpoints"])
        for n in (30, 60, 100, 200):
            self.assertTrue(J.score(rows(n))["alarm1"])
        self.assertFalse(J.score(rows(30, True))["alarm1"])
        weak = rows(30)
        for i, r in enumerate(weak):
            r["d"] = -1 if i % 2 else .9
        self.assertLess(J.score(weak)["mean_d"], 0)
        self.assertGreater(J.score(weak)["t"], -2)
        self.assertFalse(J.score(weak)["alarm1"])

    def test_effective_requires_100_and_paper(self):
        paper = {"status": "已提供", "satellite": {"sharpe": 2., "drawdown": .1}, "spy": {"sharpe": 1.}}
        for n in (30, 60, 99):
            self.assertNotEqual(J.score(rows(n, True), paper)["verdict"], "证明有效")
        self.assertEqual(J.score(rows(100, True), paper)["verdict"], "证明有效")
        self.assertNotEqual(J.score(rows(100, True))["verdict"], "证明有效")
        rs = rows(100, True)
        for r in rs[:11]:
            r["scored"] = False
        self.assertEqual(J.score(rs, paper)["verdict"], "暂停判断（对照不足）")

    def test_alarm2_strict_and_independent(self):
        for dd, expected in ((.25, False), (.2501, True)):
            out = J.score([], {"status": "已提供", "satellite": {"drawdown": dd}})
            self.assertEqual(out["alarm2"], expected)
        rs = rows(30)
        for r in rs[:4]:
            r["scored"] = False
        out = J.score(rs, {"status": "已提供", "satellite": {"drawdown": .26}})
        self.assertTrue(out["alarm2"])
        self.assertFalse(out["alarm1"])

    def test_missing_paper(self):
        self.assertEqual(J.paper_metrics(None)["status"], "未提供")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(J.paper_metrics(Path(tmp)/"absent.json")["status"], "未提供")

    def test_paper_daily_equity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"paper.json"
            data = [{"date": f"2026-10-{i+1:02}", **dict.fromkeys(("core", "satellite", "total", "spy"), v)}
                    for i, v in enumerate((100, 120, 90, 95))]
            path.write_text(json.dumps(data))
            p = J.paper_metrics(path)
            self.assertAlmostEqual(p["satellite"]["drawdown"], .25)
            self.assertAlmostEqual(p["satellite"]["return"], -.05)
            self.assertEqual(p["satellite"]["sharpe"], p["spy"]["sharpe"])
            self.assertFalse(J.score([], p)["alarm2"])

    def test_no_twins_and_market_filter(self):
        px, rec = fixture()
        row, frozen, _ = self.replay(px, rec)
        del frozen["r19"]["random_R"]
        r = J.recompute({"TEST": px["TEST"]}, [rec], [frozen], {})[0]
        self.assertEqual((J.score([r])["completed"], J.score([r])["scored"]), (1, 0))
        rec["market"]["ok"] = False
        r = J.recompute(px, [rec], [frozen], {})[0]
        self.assertEqual(J.score([r])["completed"], 0)

    def test_twin_skips_match_frozen(self):
        px, rec = fixture()
        day = rec["signal_day"]
        idx = px["TEST"]["date"].index(day)
        # Direct twin pool exercises skips even though normal eligibility filters these.
        px["T0"]["date"][idx] = "2099-01-01"
        px["T1"] = {k: v[idx-20:] for k, v in px["T1"].items()}
        for key in ("open", "high", "low", "close"):
            px["T2"][key] = [1.] * len(px["T2"][key])
        pool = ["T0", "T1", "T2", "T3"]
        # Remove the missing date rather than leaving an unsorted series.
        for key in px["T0"]:
            del px["T0"][key][idx]
        m = 1.6
        got = J.twins(px, rec, pool, m)
        done = [t["R"] for t in got if t["status"] in J.DONE]
        with patch.object(F, "PX", px):
            self.assertEqual(round(J.mean(done), 4), F._twins(rec, pool, 30, m, 3., 130))
        self.assertGreaterEqual(sum(t["status"] == "skipped" for t in got), 2)

    def test_cli_empty_writes_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / F.FOLDER
            folder.mkdir(parents=True)
            config = folder / "config.json"
            config.write_text(json.dumps({"datasets": []}))
            (folder / "outcomes.json").write_text(json.dumps({"outcomes": [], "computed_at": "2026-10-19"}))
            with patch.object(F, "ROOT", root), patch.object(F, "CONFIG", config), patch.object(F, "load_records", return_value=[]):
                J.main(["--out", str(root / "output")])
            report = json.loads((root / "output/latest.json").read_text())
            self.assertEqual(report["completed"], 0)
            self.assertIn("继续记录，未证明", (root / "output/latest.md").read_text())

    def test_jump_29_to_31_uses_exit_order(self):
        rs = rows(31)
        rs[-1]["d"] = 1000
        self.assertEqual(J.score(rs[:29])["checkpoints"], [])
        out = J.score(list(reversed(rs)))
        self.assertEqual(out["checkpoints"], J.score(rs[:30])["checkpoints"])
        self.assertEqual(out["verdict"], "失效警报1")
        self.assertGreater(out["mean_d"], 0)
        self.assertIn("| 30 | 30 | 0 |", J.markdown(out))
        self.assertIn("无冻结核对", J.markdown(out))

    def test_jump_59_to_105_judges_all_prefixes(self):
        rs = rows(105)
        self.assertEqual([c["k"] for c in J.score(rs[:59])["checkpoints"]], [30])
        out = J.score(list(reversed(rs)))
        self.assertEqual([c["k"] for c in out["checkpoints"]], [30, 60, 100])
        for cp in out["checkpoints"]:
            self.assertEqual(cp, J.score(rs[:cp["k"]])["checkpoints"][-1])
        self.assertEqual(out["verdict"], out["checkpoints"][-1]["verdict"])
        self.assertEqual(out["next_checkpoint"], 200)
        self.assertEqual([c["k"] for c in J.score(rows(305))["checkpoints"]], [30, 60, 100, 200, 300])

    def test_pause_uses_only_checkpoint_prefix(self):
        rs = rows(105)
        for r in rs[:4]:
            r["scored"] = False
        out = J.score(rs)
        self.assertEqual(out["checkpoints"][0]["verdict"], "暂停判断（对照不足）")
        self.assertEqual(out["checkpoints"][0]["unscorable"], 4)
        self.assertFalse(out["checkpoints"][0]["alarm1"])
        self.assertEqual(out["verdict"], "失效警报1")
        for r in rs:
            r["scored"] = True
        for r in rs[30:]:
            r["scored"] = False
        self.assertEqual(J.score(rs)["checkpoints"][0]["verdict"], "失效警报1")

    def test_exit_date_ties_use_id(self):
        rs = rows(31)
        for i, r in enumerate(rs):
            r["exit_date"] = "2026-10-19"
            r["id"] = f"{i:03}"
        rs[-1]["d"] = 1000
        random.Random(19).shuffle(rs)
        out = J.score(rs)
        self.assertEqual(out["checkpoints"][0]["mean_d"], J.mean([r["d"] for r in rs if r["id"] != "030"]))
        self.assertEqual(out["verdict"], "失效警报1")

    def test_zero_variance_t_unavailable(self):
        rs = rows(30)
        for r in rs:
            r["d"] = -1
        self.assertIsNone(J.score(rs)["t"])
        self.assertFalse(J.score(rs)["alarm1"])


if __name__ == "__main__":
    unittest.main()
