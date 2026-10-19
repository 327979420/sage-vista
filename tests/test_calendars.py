import unittest
from research.lab import calendars as c, app_data


class CalendarsTests(unittest.TestCase):
    def test_us_holidays(self):
        for day, following in [('2025-09-01', '2025-09-02'), ('2026-11-26', '2026-11-27'), ('2012-10-29', '2012-10-31'), ('2025-01-09', '2025-01-10')]:
            self.assertFalse(c.is_session('NYSE', day))
            self.assertEqual(c.next_session('US', day), following)
        self.assertEqual(c.previous_session('XNYS', '2025-09-02'), '2025-08-29')

    def test_hk_new_year(self):
        for day in ('2026-02-17', '2026-02-18', '2026-02-19'):
            self.assertFalse(c.is_session('HKEX', day))
        self.assertTrue(c.is_session('HK', '2026-02-16'))
        self.assertEqual(c.next_session('HK', '2026-02-16'), '2026-02-20')

    def test_month_and_boundaries(self):
        self.assertEqual(c.last_session_of_month('XNYS', '2012-10-01'), '2012-10-31')
        self.assertEqual(c.last_session_of_month('XNYS', '2026-05-01'), '2026-05-29')
        self.assertEqual(app_data.month_state({}, '2026-05-31'), ('2026-05-29', True))
        for day in ('2005-01-02', '2031-01-01', 'not-a-date'):
            with self.assertRaises(ValueError):
                c.is_session('XNYS', day)
        with self.assertRaises(ValueError):
            c.next_session('XNYS', '2030-12-31')
        with self.assertRaises(ValueError):
            c.previous_session('XNYS', '2005-01-03')
        with self.assertRaises(ValueError):
            c.is_session('BAD', '2026-10-16')

    def test_export_integrity_and_early_close(self):
        for market in ('XNYS', 'XHKG'):
            data = c._load(market)
            self.assertTrue(set(data['early_closes']) <= set(data['sessions']))
            self.assertEqual(data['header']['version'], '4.11.1')
        self.assertIn('2026-11-27', c._load('XNYS')['early_closes'])
