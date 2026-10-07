"""Frozen, content-addressed research datasets that never expire.

A dataset is the event list plus every adjusted daily bar those events need,
saved once as gzip JSON. Its SHA256 and counts are committed under
research/lab/datasets/<id>.json; the file itself lives as an asset on the
`research-datasets` GitHub release, so experiments can be re-run or extended
years later on exactly the same prices (GitHub Actions caches expire).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import pathlib
import subprocess
import tempfile

from services.scanner.macd_factor_backtest import adjusted_rows

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFESTS = ROOT / "research/lab/datasets"
RELEASE_TAG = "research-datasets"
FIELDS = ("open", "high", "low", "close", "volume")


def _compact(rows):
    return {"date": [r["date"] for r in rows], **{k: [round(float(r[k]), 6) for r in rows] for k in FIELDS}}


def expand(series):
    return [{"date": d, **{k: series[k][i] for k in FIELDS}} for i, d in enumerate(series["date"])]


def build_from_ledger(ledger_path, cache_dir, dataset_id, signal_from=None):
    """Production ledger events with their frozen support plans and cached prices.

    `signal_from` keeps only later signals, for a forward holdout that is
    registered before its data exists.
    """
    ledger = json.loads(pathlib.Path(ledger_path).read_text())
    events, prices = [], {}
    for e in ledger["events"]:
        sel = e.get("selection") or {}
        if sel.get("exclude_from_effectiveness") or not sel.get("support_plan"):
            continue
        if signal_from and e["signal_date"] < signal_from:
            continue
        events.append({"event_id": e["event_id"], "symbol": e["symbol"], "signal_date": e["signal_date"], "support_plan": sel["support_plan"]})
    for symbol in sorted({e["symbol"] for e in events}):
        path = pathlib.Path(cache_dir) / f"{symbol}.json"
        if path.exists():
            prices[symbol] = _compact(adjusted_rows(json.loads(path.read_text())))
    events = [e for e in events if e["symbol"] in prices]
    return {"dataset_id": dataset_id, "source": "public/opportunity-ledger.json + work/eodhd-cache (adjusted_rows)",
            "price_basis": "EODHD adjusted daily OHLCV", "events": events, "prices": prices}


def build_from_observation(trades_csv, dataset_id, fetch):
    """The 20-year observation events, with full price histories fetched once."""
    events = {}
    with open(trades_csv, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            key = (row["symbol"], row["signal_date"], row["episode_id"])
            events.setdefault(key, {"event_id": f"{row['symbol']}-{row['signal_date']}-{row['episode_id']}", "symbol": row["symbol"],
                                    "signal_date": row["signal_date"], "timeframe": row["timeframe"], "score": float(row["score"] or 0)})
    prices = {}
    for symbol in sorted({e["symbol"] for e in events.values()}):
        try:
            rows = adjusted_rows(fetch(symbol))
        except Exception:  # keep going; missing symbols are counted, not hidden
            rows = []
        if rows:
            prices[symbol] = _compact(rows)
    kept = [e for e in events.values() if e["symbol"] in prices]
    return {"dataset_id": dataset_id, "source": f"{trades_csv} events + EODHD full adjusted history",
            "price_basis": "EODHD adjusted daily OHLCV", "missing_symbols": sorted({e['symbol'] for e in events.values()} - set(prices)),
            "events": kept, "prices": prices}


def build_from_symbols(symbols, dataset_id, fetch):
    """Reference series only (for example SPY as the benchmark); no events."""
    prices = {}
    for symbol in symbols:
        rows = adjusted_rows(fetch(symbol))
        if not rows:
            raise ValueError(f"benchmark_prices_missing: {symbol}")
        prices[symbol] = _compact(rows)
    return {"dataset_id": dataset_id, "source": f"EODHD full adjusted history for {', '.join(symbols)}",
            "price_basis": "EODHD adjusted daily OHLCV", "events": [], "prices": prices}


def save(dataset, out_dir):
    raw = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode()
    blob = gzip.compress(raw, 9, mtime=0)
    sha = hashlib.sha256(blob).hexdigest()
    asset = f"{dataset['dataset_id']}-{sha[:12]}.json.gz"
    path = pathlib.Path(out_dir) / asset
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    manifest = {"dataset_id": dataset["dataset_id"], "asset": asset, "sha256": sha, "bytes": len(blob), "release": RELEASE_TAG,
                "events": len(dataset["events"]), "symbols": len(dataset["prices"]), "source": dataset["source"],
                "price_basis": dataset["price_basis"], "missing_symbols": len(dataset.get("missing_symbols", []))}
    return path, manifest


def load(path, sha256):
    blob = pathlib.Path(path).read_bytes()
    if hashlib.sha256(blob).hexdigest() != sha256:
        raise ValueError(f"dataset_hash_mismatch: {path}")
    return json.loads(gzip.decompress(blob))


def manifest(dataset_id):
    path = MANIFESTS / f"{dataset_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def upload(path):
    """Upload once; an existing asset is never overwritten, only verified."""
    path = pathlib.Path(path)
    view = subprocess.run(["gh", "release", "view", RELEASE_TAG, "--json", "assets", "-q", ".assets[].name"], capture_output=True, text=True)
    if view.returncode != 0:
        subprocess.run(["gh", "release", "create", RELEASE_TAG, "--prerelease", "--title", "Research datasets",
                        "--notes", "Frozen, content-addressed research datasets. Assets are never replaced."], check=True)
    elif path.name in view.stdout.split():
        # Same name means same SHA256 prefix; confirm the full hash before reusing it.
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run(["gh", "release", "download", RELEASE_TAG, "-p", path.name, "-D", folder], check=True)
            remote = hashlib.sha256((pathlib.Path(folder) / path.name).read_bytes()).hexdigest()
        if remote != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"release_asset_conflict: {path.name}")
        return
    subprocess.run(["gh", "release", "upload", RELEASE_TAG, str(path)], check=True)


def download(entry, out_dir):
    out = pathlib.Path(out_dir) / entry["asset"]
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["gh", "release", "download", entry["release"], "-p", entry["asset"], "-D", str(out.parent)], check=True)
    return out
