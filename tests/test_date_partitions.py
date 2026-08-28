import unittest

from services.scanner.date_partitions import weekly_partitions


class DatePartitionTests(unittest.TestCase):
    def test_any_range_is_split_at_week_boundaries(self):
        parts = weekly_partitions("2026-07-01", "2026-07-14")
        self.assertEqual(parts, [
            {"label": "2026-07-01_to_2026-07-05", "start": "2026-07-01", "end": "2026-07-05"},
            {"label": "2026-07-06_to_2026-07-12", "start": "2026-07-06", "end": "2026-07-12"},
            {"label": "2026-07-13_to_2026-07-14", "start": "2026-07-13", "end": "2026-07-14"},
        ])

    def test_invalid_range_fails_before_starting_workers(self):
        with self.assertRaises(ValueError):
            weekly_partitions("2026-08-02", "2026-08-01")


if __name__ == "__main__":
    unittest.main()
