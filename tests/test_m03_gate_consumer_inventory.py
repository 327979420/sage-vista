"""Freeze legacy gate-like consumers until their owning modules migrate them."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOKENS = (
    "long_trend_ok(",
    "exact_daily_macd_bull_cross(",
    "macd_buy_gate(",
    '"qualification.long_trend"',
    '"macd.daily_bull_cross"',
    "recent_macd_bull_cross",
    "_bull_crosses(",
)

# factor_registry declares facts; it does not consume or create a candidate.
DECLARATION_ONLY = {"services/scanner/factor_registry.py"}
EXPECTED_LEGACY_CONSUMER_FILES = {
    "services/scanner/factor_detectors.py",
    "services/scanner/factor_effectiveness.py",
    "services/scanner/factor_snapshot.py",
    "services/scanner/favorite_pattern_tracker.py",
    "services/scanner/macd_factor_backtest.py",
    "services/scanner/rare_opportunity_scanner.py",
    "services/scanner/resonance_tracker.py",
    "services/scanner/theme_etf_context.py",
    "services/scanner/unified_v2_scan.py",
}


class M03GateConsumerInventoryTests(unittest.TestCase):
    def test_every_gate_like_scanner_is_deliberately_registered(self):
        found = set()
        for path in sorted((ROOT / "services/scanner").glob("*.py")):
            relative = str(path.relative_to(ROOT))
            if any(token in path.read_text() for token in TOKENS):
                found.add(relative)
        self.assertEqual(found - DECLARATION_ONLY, EXPECTED_LEGACY_CONSUMER_FILES)

    def test_only_sole_producer_assigns_new_m03_gate_identity(self):
        creators = set()
        for path in sorted((ROOT / "services").rglob("*.py")):
            relative = str(path.relative_to(ROOT))
            if '"gate_event_id": event_id' in path.read_text():
                creators.add(relative)
        self.assertEqual(creators, {"services/gates/producer.py"})


if __name__ == "__main__":
    unittest.main()

