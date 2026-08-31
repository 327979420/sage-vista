import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest

from services.contracts import ContractError, stable_instrument_id, validate_revision_chain
from services.market_data import MarketDataRepository


ROOT = Path(__file__).resolve().parents[1]


def bar(day, close=100.0, volume=1000):
    return {
        "date": day,
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "adjusted_close": close,
        "volume": volume,
    }


class FakeSource:
    def __init__(self, rows, *, delay=0.0, extra_rows=()):
        self.rows = {row["date"]: copy.deepcopy(row) for row in rows}
        self.delay = delay
        self.extra_rows = list(extra_rows)
        self.calls = []
        self._lock = threading.Lock()

    def fetch(self, instrument_id, dates):
        with self._lock:
            self.calls.append((instrument_id, dates))
        if self.delay:
            time.sleep(self.delay)
        rows = [copy.deepcopy(self.rows[day]) for day in dates] + copy.deepcopy(self.extra_rows)
        return sorted(rows, key=lambda row: row["date"])


class MarketDataRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.instrument_id = stable_instrument_id(
            provider="EODHD", market="US", provider_code="ABC", listing_lifecycle="listing-1"
        )
        self.days = ["2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"]
        self.rows = [bar(day, 100 + index) for index, day in enumerate(self.days)]

    @staticmethod
    def cache_file(root):
        files = list((Path(root) / "instruments").glob("*.json"))
        if len(files) != 1:
            raise AssertionError(f"expected one cache file, found {files}")
        return files[0]

    def test_complete_cache_never_calls_source_and_repeat_is_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            repository = MarketDataRepository(folder, source)
            first = repository.read(
                self.instrument_id, as_of=self.days[-1], required_dates=self.days
            )
            before = self.cache_file(folder).read_bytes()
            source.calls.clear()
            second = repository.read(
                self.instrument_id, as_of=self.days[-1], required_dates=self.days
            )
            self.assertEqual(source.calls, [])
            self.assertEqual(first, second)
            self.assertEqual(self.cache_file(folder).read_bytes(), before)

    def test_only_head_tail_and_middle_gaps_are_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            repository = MarketDataRepository(folder, source)
            repository.read(
                self.instrument_id,
                as_of=self.days[-1],
                required_dates=(self.days[1], self.days[3]),
            )
            source.calls.clear()
            result = repository.read(
                self.instrument_id, as_of=self.days[-1], required_dates=self.days
            )
            self.assertEqual(source.calls[0][1], (self.days[0], self.days[2], self.days[4]))
            self.assertEqual([row["date"] for row in result.rows], self.days)

    def test_two_concurrent_requests_perform_one_actual_fill(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows, delay=0.05)
            first = MarketDataRepository(folder, source)
            second = MarketDataRepository(folder, source)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        repository.read,
                        self.instrument_id,
                        as_of=self.days[-1],
                        required_dates=self.days,
                    )
                    for repository in (first, second)
                ]
                results = [future.result() for future in futures]
            self.assertEqual(len(source.calls), 1)
            self.assertEqual(results[0], results[1])

    def test_failure_before_replace_keeps_old_cache_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            MarketDataRepository(folder, source).read(
                self.instrument_id, as_of=self.days[-1], required_dates=(self.days[0],)
            )
            path = self.cache_file(folder)
            before = path.read_bytes()

            def fail(_target, _temporary):
                raise RuntimeError("injected-before-replace-failure")

            failing = MarketDataRepository(folder, source, before_replace=fail)
            with self.assertRaisesRegex(RuntimeError, "injected-before-replace"):
                failing.read(
                    self.instrument_id,
                    as_of=self.days[-1],
                    required_dates=(self.days[0], self.days[1]),
                )
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_invalid_new_data_is_rejected_without_touching_old_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            initial = FakeSource(self.rows)
            MarketDataRepository(folder, initial).read(
                self.instrument_id, as_of=self.days[-1], required_dates=(self.days[0],)
            )
            path = self.cache_file(folder)
            before = path.read_bytes()
            invalid = copy.deepcopy(self.rows[1])
            invalid["high"] = invalid["low"] - 1
            source = FakeSource([invalid])
            with self.assertRaises(ContractError):
                MarketDataRepository(folder, source).read(
                    self.instrument_id,
                    as_of=self.days[-1],
                    required_dates=(self.days[0], self.days[1]),
                )
            self.assertEqual(path.read_bytes(), before)

    def test_source_cannot_overwrite_unconfirmed_history_or_return_extra_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            initial = FakeSource(self.rows)
            MarketDataRepository(folder, initial).read(
                self.instrument_id, as_of=self.days[-1], required_dates=(self.days[0],)
            )
            path = self.cache_file(folder)
            before = path.read_bytes()
            changed_old = bar(self.days[0], 999)
            malicious = FakeSource(self.rows, extra_rows=[changed_old])
            with self.assertRaisesRegex(ContractError, "exactly the requested"):
                MarketDataRepository(folder, malicious).read(
                    self.instrument_id,
                    as_of=self.days[-1],
                    required_dates=(self.days[0], self.days[1]),
                )
            self.assertEqual(path.read_bytes(), before)

    def test_as_of_after_rows_are_never_returned(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            repository = MarketDataRepository(folder, source)
            earlier = repository.read(
                self.instrument_id, as_of=self.days[2], required_dates=self.days[:3]
            )
            repository.read(self.instrument_id, as_of=self.days[-1], required_dates=self.days)
            result = repository.read(self.instrument_id, as_of=self.days[2])
            self.assertEqual([row["date"] for row in result.rows], self.days[:3])
            self.assertEqual(result.point_in_time_fingerprint, earlier.point_in_time_fingerprint)
            with self.assertRaises(ContractError):
                repository.read(
                    self.instrument_id,
                    as_of=self.days[2],
                    required_dates=(self.days[3],),
                )

    def test_supplier_changes_create_complete_append_only_revision_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            repository = MarketDataRepository(folder, source)
            repository.read(
                self.instrument_id, as_of=self.days[-1], required_dates=self.days[:2]
            )
            source.rows[self.days[0]] = bar(self.days[0], 99)
            first = repository.read(
                self.instrument_id, as_of=self.days[-1], refresh_dates=(self.days[0],)
            )
            first_records = self._revision_records(folder)
            source.rows[self.days[0]] = bar(self.days[0], 98)
            second = repository.read(
                self.instrument_id, as_of=self.days[-1], refresh_dates=(self.days[0],)
            )
            second_records = self._revision_records(folder)
            self.assertEqual(len(first_records), 1)
            self.assertEqual(len(second_records), 2)
            self.assertEqual(second_records[0], first_records[0])
            record = second_records[-1]
            self.assertEqual(record["instrument_id"], self.instrument_id)
            self.assertEqual(record["changed_date"], self.days[0])
            self.assertEqual(record["old_row"]["close"], 99)
            self.assertEqual(record["new_row"]["close"], 98)
            self.assertTrue(record["before_fingerprint"].startswith("sha256:"))
            self.assertTrue(record["after_fingerprint"].startswith("sha256:"))
            self.assertEqual(
                record["previous_revision_fingerprint"],
                second_records[0]["revision_fingerprint"],
            )
            self.assertEqual(record["reconstruction_status"], "reconstructible")
            validate_revision_chain(second_records)

    def test_unreconstructible_revision_is_explicit_and_explained(self):
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            repository = MarketDataRepository(folder, source)
            repository.read(
                self.instrument_id, as_of=self.days[-1], required_dates=(self.days[0],)
            )
            source.rows[self.days[0]] = bar(self.days[0], 97)
            result = repository.read(
                self.instrument_id,
                as_of=self.days[-1],
                refresh_dates=(self.days[0],),
                revision_reconstructible=False,
                reconstruction_reason="The imported legacy origin has no earlier full-history fingerprint.",
            )
            self.assertEqual(len(result.rows), 1)
            record = self._revision_records(folder)[0]
            self.assertEqual(record["reconstruction_status"], "not_reconstructible")
            self.assertIn("legacy origin", record["reconstruction_reason"])

    def test_unsafe_instrument_ids_fail_before_any_source_or_path_access(self):
        invalid = (
            "../public/data.json",
            "/tmp/data.json",
            r"C:\\cache\\data.json",
            "instrument:sha256:../../escape",
            "instrument:sha256:ABC",
        )
        with tempfile.TemporaryDirectory() as folder:
            source = FakeSource(self.rows)
            repository = MarketDataRepository(folder, source)
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(ContractError):
                    repository.read(value, as_of=self.days[-1], required_dates=(self.days[0],))
            self.assertEqual(source.calls, [])
            self.assertFalse((Path(folder) / "instruments").exists())

    def test_shadow_root_guard_runs_before_provider_calls_or_file_creation(self):
        source = FakeSource(self.rows)
        prohibited = (
            ROOT,
            ROOT / "public",
            ROOT / "automation",
            ROOT / "not-approved-shadow-cache",
        )
        children = tuple(
            child
            for root in prohibited
            for child in (root / "instruments", root / ".locks")
        )
        before = {path: path.exists() for path in children}
        for root in prohibited:
            with self.subTest(root=root), self.assertRaisesRegex(
                ContractError, "temp or workspace work"
            ):
                MarketDataRepository(root, source, workspace_root=ROOT)
        self.assertEqual(source.calls, [])
        self.assertEqual({path: path.exists() for path in children}, before)

        with tempfile.TemporaryDirectory(dir=ROOT / "work") as folder:
            repository = MarketDataRepository(folder, source, workspace_root=ROOT)
            result = repository.read(
                self.instrument_id,
                as_of=self.days[0],
                required_dates=(self.days[0],),
            )
            self.assertEqual([row["date"] for row in result.rows], [self.days[0]])

    @classmethod
    def _revision_records(cls, root):
        import json

        return json.loads(cls.cache_file(root).read_text())["revision_log"]


if __name__ == "__main__":
    unittest.main()
