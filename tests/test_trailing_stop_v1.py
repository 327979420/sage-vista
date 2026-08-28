import unittest

from research.backtest.trailing_stop_v1 import simulate


class TrailingStopTest(unittest.TestCase):
    def test_breakeven_activates_next_day(self):
        path = [
            {"date":"d1","open":100,"low":99,"high":111,"close":110},
            {"date":"d2","open":101,"low":99,"high":102,"close":101},
        ]
        result = simulate(100, 90, 120, path, "breakeven_1r")
        self.assertEqual(result["reason"], "stop")
        self.assertEqual(result["return"], 0)

    def test_activation_close_does_not_rewrite_same_bar(self):
        path = [{"date":"d1","open":100,"low":95,"high":112,"close":110}]
        self.assertIsNone(simulate(100, 90, 120, path, "breakeven_1r"))


if __name__ == "__main__":
    unittest.main()
