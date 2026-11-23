import gzip
import hashlib
import json
import pathlib
import tempfile
import unittest

from services.scanner import public_store
from services.scanner.daily_tracker_update import read_json, write_history_asset

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PublicStoreTests(unittest.TestCase):
    def test_archives_over_the_github_limit_are_stored_compressed(self):
        self.assertEqual(public_store.STORED_COMPRESSED, {"signal-history.json", "unified-v2-rankings.json"})
        for name in public_store.STORED_COMPRESSED:
            self.assertFalse((ROOT / "public" / name).exists(), name)
            stored = ROOT / "public" / f"{name}.gz"
            self.assertLess(stored.stat().st_size, 100 * 1024 * 1024)
            payload = public_store.read_json(ROOT / "public" / name)
            self.assertIn("generated_at", payload)

    def test_round_trip_keeps_exact_bytes_and_is_deterministic(self):
        content = json.dumps({"cases": ["历史" * 500]}, ensure_ascii=False, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "signal-history.json"
            self.assertFalse(public_store.exists(path))
            stored = public_store.write_bytes(path, content)
            self.assertEqual(stored.name, "signal-history.json.gz")
            self.assertFalse(path.exists())
            self.assertTrue(public_store.exists(path))
            self.assertEqual(public_store.read_bytes(path), content)
            first = hashlib.sha256(stored.read_bytes()).hexdigest()
            public_store.write_bytes(path, content)
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), first)

    def test_plain_files_and_old_plain_archives_are_read_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            other = pathlib.Path(folder) / "update-status.json"
            self.assertEqual(public_store.write_text(other, "{}"), other)
            self.assertEqual(other.read_text(), "{}")
            legacy = pathlib.Path(folder) / "unified-v2-rankings.json"
            legacy.write_text('{"days":[]}')
            self.assertEqual(public_store.read_json(legacy), {"days": []})

    def test_both_forms_present_fails_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "signal-history.json"
            public_store.write_text(path, '{"as_of":"new"}')
            path.write_text('{"as_of":"stale"}')
            with self.assertRaisesRegex(RuntimeError, "Both"):
                public_store.read_json(path)

    def test_replace_moves_the_stored_form_and_removes_a_stale_plain_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = pathlib.Path(folder)
            (folder / "work").mkdir(); (folder / "public").mkdir()
            public_store.write_text(folder / "work/signal-history.json", '{"as_of":"2026-11-20"}')
            (folder / "public/signal-history.json").write_text('{"as_of":"old"}')
            public_store.replace(folder / "work/signal-history.json", folder / "public/signal-history.json")
            self.assertFalse((folder / "public/signal-history.json").exists())
            self.assertEqual(public_store.read_json(folder / "public/signal-history.json"), {"as_of": "2026-11-20"})

    def test_daily_update_reads_and_writes_the_history_archive(self):
        history = {"as_of": "2026-11-20", "cases": [{"signal_id": "x", "daily_states": [{"date": "2026-11-20"}]}]}
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "signal-history.json"
            self.assertEqual(read_json(path), {})
            write_history_asset(path, history)
            self.assertEqual(gzip.decompress((pathlib.Path(folder) / "signal-history.json.gz").read_bytes()),
                             json.dumps(history, ensure_ascii=False, separators=(",", ":")).encode())
            self.assertEqual(read_json(path), history)


if __name__ == "__main__":
    unittest.main()
