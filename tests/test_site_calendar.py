"""The site's data pill keeps its own copy of NYSE closures; it must equal the verified calendar."""
import datetime as dt
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteCalendarTests(unittest.TestCase):
    def test_site_closures_match_calendar(self):
        source = (ROOT / 'app/data-freshness.ts').read_text()
        block = re.search(r'NYSE_CLOSED = new Set\(\[(.*?)\]\)', source, re.S).group(1)
        listed = re.findall(r"'(\d{4}-\d{2}-\d{2})'", block)
        calendar = json.loads((ROOT / 'data/calendars/xnys-2005-2030.json').read_text())
        sessions, day, end, closed = set(calendar['sessions']), dt.date(2026, 1, 1), dt.date.fromisoformat(calendar['header']['end']), []
        while day <= end:
            if day.weekday() < 5 and day.isoformat() not in sessions:
                closed.append(day.isoformat())
            day += dt.timedelta(days=1)
        self.assertEqual(listed, closed)


if __name__ == '__main__':
    unittest.main()
