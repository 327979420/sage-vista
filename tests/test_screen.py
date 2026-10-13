import pathlib
import tempfile
import unittest

from research.lab import screen


def raw(days, close, volume):
    return [{"date": d, "open": close, "high": close, "low": close, "close": close, "adjusted_close": close, "volume": volume} for d in days]


class ScreenTests(unittest.TestCase):
    LISTED = [{"Code": "AAA", "Type": "Common Stock", "Exchange": "NYSE"}, {"Code": "BBB", "Type": "Common Stock", "Exchange": "NASDAQ"},
              {"Code": "ETF", "Type": "ETF", "Exchange": "NYSE ARCA"}, {"Code": "OTC", "Type": "Common Stock", "Exchange": "PINK"},
              {"Code": "OLD", "Type": "Common Stock", "Exchange": "NYSE"}]
    DELISTED = [{"Code": "CCC", "Type": "Common Stock", "Exchange": "NASDAQ"}, {"Code": "OLD", "Type": "Common Stock", "Exchange": "AMEX"}]

    def test_candidates_are_primary_common_stocks_without_reused_or_known_tickers(self):
        names, counts = screen.candidates(self.LISTED, self.DELISTED, exclude={"BBB"})
        self.assertEqual(names, ["AAA", "CCC"])
        self.assertEqual(counts, {"listed": 3, "delisted": 2, "reused": 1})

    def test_a_stock_is_kept_only_with_enough_pool_sessions_and_failures_are_counted(self):
        days = [f"2010-01-{d:02d}" for d in range(1, 29)]
        prices = {"AAA": raw(days, 20.0, 1_000_000), "CCC": raw(days, 4.0, 10_000_000), "DDD": raw(["2004-06-01"] + days[:5], 20.0, 1_000_000)}

        def fetch(symbol):
            if symbol == "EEE":
                raise RuntimeError("provider failed")
            return prices[symbol]
        pool = {"min_close": 5.0, "min_dollar_volume": 1e7}
        kept, stats, failed = screen.screen(["AAA", "CCC", "DDD", "EEE"], fetch, ("2005-01-01", "2025-06-30"), pool, 10, workers=2)
        self.assertEqual(kept, ["AAA"])                # CCC is under $5, DDD has only 5 good sessions
        self.assertEqual(stats["DDD"]["good_sessions"], 5)
        self.assertEqual(failed, ["EEE"])

    def test_a_run_writes_alphabetical_shards_and_a_verdict(self):
        days = [f"2010-02-{d:02d}" for d in range(1, 29)]
        listed = [{"Code": c, "Type": "Common Stock", "Exchange": "NYSE"} for c in ("ZZ", "AB", "MM", "KN")]
        spec = {"id": "s", "experiment_id": "s", "group": "data", "question": "q", "fetch_start": "2004-01-01", "window": ["2005-01-01", "2025-06-30"],
                "pool": {"min_close": 5.0, "min_dollar_volume": 1e7}, "min_sessions": 10, "shard_size": 2, "shard_dir": "u", "shard_prefix": "fresh",
                "criteria": {"max_failed_share": 0.1, "min_kept": 3}}
        entry = {"dataset_id": "d", "asset": "a", "sha256": "x", "symbols": 1}
        with tempfile.TemporaryDirectory() as root:
            result, stats, failed = screen.run(spec, {"prices": {"KN": {}}}, entry, root, listed=listed, delisted=[],
                                               fetch=lambda s: raw(days, 30.0, 1_000_000))
            self.assertEqual([x["symbols"] for x in result["shards"]], [2, 1])
            self.assertEqual(pathlib.Path(root, "u", "fresh-a.txt").read_text().split(), ["AB", "MM"])
            self.assertEqual(pathlib.Path(root, "u", "fresh-b.txt").read_text().split(), ["ZZ"])
            self.assertTrue(result["passed"])
            self.assertTrue(screen.render(result).startswith("# s"))


class V3WeeklyHelperTests(unittest.TestCase):
    def test_engulfing_zone_and_macd_helpers(self):
        from research.lab import v3weekly as V
        rows = [{"open": 10, "high": 10.5, "low": 9.5, "close": 9.6}, {"open": 9.55, "high": 10.8, "low": 9.4, "close": 10.4},
                {"open": 10.4, "high": 10.6, "low": 9.9, "close": 10.1}]
        self.assertTrue(V.bullish_engulf(rows, 1))
        self.assertFalse(V.bullish_engulf(rows, 2))
        lows = [{"low": x} for x in (12, 10.3, 10.0, 10.5, 13, 14)]
        self.assertEqual(V.zone(lows, 2, 0.06), (1, 3))
        hist = [-5, -4, -3, -1.0]
        self.assertEqual(V.macd_ok(hist, [0, 0, 0, -1], [0, 0, 0, 0], 3), "about")
        self.assertEqual(V.macd_ok(hist, [0, 0, 0, 1], [0, 0, 0, 0], 3), "crossed")
        self.assertIsNone(V.macd_ok([-5, -4, -4.5, -3], [0, 0, 0, -1], [0, 0, 0, 0], 3))


if __name__ == "__main__":
    unittest.main()
