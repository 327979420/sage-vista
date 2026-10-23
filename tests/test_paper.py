import json
import pathlib
import unittest

from research.lab import calendars, paper

CONFIG = json.loads((pathlib.Path(__file__).resolve().parents[1] / "research/lab/paper/config.json").read_text())
SLEEVES = CONFIG["core"]["sleeves"]


def sessions(start, end):
    out, day = [], start
    if not calendars.is_session("XNYS", day):
        day = calendars.next_session("XNYS", day)
    while day <= end:
        out.append(day)
        day = calendars.next_session("XNYS", day)
    return out


DAYS = sessions("2025-06-02", "2026-11-30")


def series(prices):
    return {"date": list(DAYS), "open": list(prices), "high": [p * 1.01 for p in prices], "low": [p * 0.99 for p in prices],
            "close": list(prices), "volume": [1000] * len(prices)}


def book(down=()):
    """Every sleeve rises 0.05% a session; those in `down` fall 0.05% a session. SHY is flat at 100."""
    out = {}
    for s in SLEEVES:
        step = 0.9995 if s in down else 1.0005
        out[s] = series([50 * step ** i for i in range(len(DAYS))])
    out["SHY"] = series([100.0] * len(DAYS))
    return out


class CalendarTests(unittest.TestCase):
    def test_month_end_and_first_signal(self):
        self.assertTrue(paper.is_month_end("2026-09-30"))
        self.assertFalse(paper.is_month_end("2026-09-29"))
        self.assertTrue(paper.is_month_end("2026-10-30"))
        self.assertEqual(paper.signal_month_end(CONFIG["start"]), "2026-09-30")

    def test_registered_before_start(self):
        self.assertLess(CONFIG["registered"], CONFIG["start"])
        self.assertTrue(calendars.is_session("XNYS", CONFIG["start"]))


class CoreTests(unittest.TestCase):
    def test_equal_to_sma_is_not_above(self):
        prices = {"X": series([10.0] * len(DAYS))}
        self.assertFalse(paper.above_sma(prices, "X", "2026-09-30"))

    def test_short_history_and_missing_price_stop_the_run(self):
        prices = {"X": series([10.0] * len(DAYS))}
        with self.assertRaises(ValueError):
            paper.above_sma(prices, "X", DAYS[10])
        with self.assertRaises(ValueError):
            paper.bar(prices, "X", "2030-01-02")

    def test_rebalance_on_start_then_after_month_end(self):
        prices = book(down={"XLU", "XLY"})
        dates = [d for d in DAYS if "2026-10-26" <= d <= "2026-11-05"]
        run = paper.run_core(prices, dates, SLEEVES, "SHY", 50000, 0.001, "2026-09-30")
        first, second = run["rebalances"][0], run["rebalances"][1]
        self.assertEqual(first["date"], "2026-10-26")
        self.assertEqual(first["signal"], "2026-09-30")
        self.assertEqual(first["targets"]["XLU"], "SHY")
        self.assertEqual(first["targets"]["XLK"], "XLK")
        self.assertEqual(second["signal"], "2026-10-30")
        self.assertEqual(second["date"], "2026-11-02")
        # Two sleeves in SHY: about 20% of the core sits in SHY after the first rebalance.
        shy_value = first["shares"]["SHY"] * 100
        self.assertAlmostEqual(shy_value / 50000, 0.2, delta=0.01)
        self.assertGreaterEqual(min(run["equity"]), 0)

    def test_switch_from_etf_to_shy_sells_first(self):
        prices = book()
        # XLE turns down from September 2026 onward, so the October month-end signal moves it to SHY.
        i0 = DAYS.index("2026-09-01")
        closes = [50 * 1.0005 ** i for i in range(len(DAYS))]
        closes = closes[:i0] + [closes[i0] * 0.98 ** (i - i0 + 1) for i in range(i0, len(DAYS))]
        prices["XLE"] = series(closes)
        dates = [d for d in DAYS if "2026-10-26" <= d <= "2026-11-03"]
        run = paper.run_core(prices, dates, SLEEVES, "SHY", 50000, 0.001, "2026-09-30")
        self.assertEqual(run["rebalances"][-1]["targets"]["XLE"], "SHY")
        self.assertNotIn("XLE", run["shares"])
        self.assertGreater(run["cash"], -1e-9)


class SatelliteTests(unittest.TestCase):
    def candidate(self, event, symbol, entry_date, entry, stop, exit_date=None, exit_price=None, closes=None):
        return {"event_id": event, "symbol": symbol, "signal_date": entry_date, "priority": 0, "entry_date": entry_date,
                "entry_price": entry, "stop": stop, "fills": [(exit_date, exit_price, 1.0)] if exit_date else [],
                "data_ended": False, "closes": closes or [(entry_date, entry)]}

    def test_sizing_stop_target_and_open(self):
        dates = [d for d in DAYS if "2026-10-26" <= d <= "2026-11-06"]
        stop = self.candidate("a", "AAA", dates[1], 100.0, 90.0, dates[3], 90.0, [(d, 100.0) for d in dates[1:4]])
        target = self.candidate("b", "BBB", dates[2], 50.0, 45.0, dates[5], 65.0, [(d, 50.0) for d in dates[2:6]])
        still_open = self.candidate("c", "CCC", dates[4], 20.0, 19.0, closes=[(d, 21.0) for d in dates[4:]])
        run = paper.run_satellite([stop, target, still_open], dates, 50000, 0.001)
        booked = {t["event_id"]: t for t in run["trades"]}
        # Risk 2% of $50k = $1,000 over a $10 risk -> 100 shares, under the 20% cap ($10,000 / $100 = 100 shares).
        self.assertEqual(booked["a"]["shares"], 100)
        self.assertLess(booked["a"]["pnl"], 0)
        self.assertGreater(booked["b"]["pnl"], 0)
        self.assertEqual(run["open_at_end"], 1)
        self.assertEqual(len(run["equity"]), len(dates))

    def test_heat_cap_skips_new_risk(self):
        dates = [d for d in DAYS if "2026-10-26" <= d <= "2026-11-06"]
        many = [self.candidate(f"e{i}", f"S{i}", dates[1], 10.0, 5.0, closes=[(d, 10.0) for d in dates[1:]]) for i in range(12)]
        run = paper.run_satellite(many, dates, 50000, 0.001)
        # Risk binds: 2% of $50k = $1,000 / $5 = 200 shares (cap would allow 1,000), so each uses 2% heat;
        # the 10% heat cap allows five, the rest are skipped.
        self.assertEqual(run["open_at_end"], 5)
        self.assertGreater(run["skipped"].get("open_risk_limit", 0), 0)


class ComputeTests(unittest.TestCase):
    def test_series_shape_and_totals(self):
        prices = book(down={"XLU"})
        snap = paper.compute({**CONFIG, "start": "2026-10-26"}, prices, [])
        row = snap["series"][0]
        self.assertEqual(row["date"], "2026-10-26")
        self.assertEqual(set(row), {"date", "core", "satellite", "total", "spy"})
        for r in snap["series"]:
            self.assertAlmostEqual(r["total"], r["core"] + r["satellite"], places=1)
        self.assertEqual(snap["series"][-1]["satellite"], 50000.0)

    def test_nothing_before_the_first_session(self):
        prices = book()
        self.assertIsNone(paper.compute({**CONFIG, "start": "2026-12-01"}, prices, []))


if __name__ == "__main__":
    unittest.main()


class CandidateTests(unittest.TestCase):
    def test_rows_from_forward_judge_become_candidates(self):
        dates = [d for d in DAYS if "2026-10-20" <= d <= "2026-11-10"]
        px = {"AAA": {"date": dates, "close": [100.0 + i for i in range(len(dates))]}}
        base = {"symbol": "AAA", "signal_day": dates[0], "eligible": True}
        rows = [
            {**base, "id": "done", "trade": {"fill_day": 5, "entry": 101.0, "stop": 95.0, "status": "loss", "exit_day": 8, "exit": 95.0}},
            {**base, "id": "open", "trade": {"fill_day": 6, "entry": 102.0, "stop": 96.0, "status": "open", "exit_day": len(dates) - 1, "exit": 0}},
            {**base, "id": "before", "trade": {"fill_day": 1, "entry": 99.0, "stop": 90.0, "status": "win", "exit_day": 9, "exit": 120.0}},
            {**base, "id": "waiting", "trade": {"status": "waiting"}},
            {**base, "id": "filtered", "eligible": False, "trade": {"fill_day": 5, "entry": 1.0, "stop": 0.5, "status": "win", "exit_day": 6, "exit": 2.0}},
        ]
        out = {c["event_id"]: c for c in paper.satellite_candidates(px, rows, "2026-10-26")}
        self.assertEqual(set(out), {"done", "open"})
        self.assertEqual(out["done"]["fills"], [(dates[8], 95.0, 1.0)])
        self.assertEqual(out["open"]["fills"], [])
        self.assertEqual(out["open"]["closes"][-1][0], dates[-1])
