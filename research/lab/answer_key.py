"""Score a buy-point detector against the user's answer key (research/lab/cases/triangle-answer-key-v1.json).

    python3 -m research.lab.answer_key            # uses research.lab.triangle
"""
import datetime as dt
import json
import pathlib

KEY = pathlib.Path(__file__).resolve().parent / "cases" / "triangle-answer-key-v1.json"


def score(scan, key=None):
    """scan(symbol) -> candidates with options {name: {fill, stop, ...}}. Returns per-case rows and the hit count."""
    key = key or json.loads(KEY.read_text())
    rows, hits = [], 0
    for case in key["cases"]:
        found = []
        for c in scan(case["symbol"]):
            for name, o in c["options"].items():
                for lo, hi in case["windows"]:
                    if lo <= o["fill"] <= (dt.date.fromisoformat(hi) + dt.timedelta(days=4)).isoformat():
                        found.append((name, o))
        if case["expect"] == "none":
            ok = not found
        else:
            ok = bool(found)
            if ok and case.get("stop"):
                ok = any(abs(o["stop"] / case["stop"] - 1) <= 0.03 for _, o in found)
        hits += ok
        rows.append({"symbol": case["symbol"], "expect": case["expect"], "ok": ok, "found": [(n, o["fill"], o["entry"], o["stop"]) for n, o in found],
                     "near": sorted({o["fill"] for c in scan(case["symbol"]) for o in c["options"].values()
                                     if abs((dt.date.fromisoformat(o["fill"]) - dt.date.fromisoformat(case["windows"][0][0])).days) < 200})})
    return rows, hits


if __name__ == "__main__":
    from research.lab import datasets, triangle
    e = datasets.manifest("universe-1985-v1")
    triangle.PRICES = datasets.load("work/lab/" + e["asset"], e["sha256"])["prices"]
    cache = {}
    scan = lambda s: cache.setdefault(s, triangle.scan_symbol(s))
    rows, hits = score(scan)
    for r in rows:
        print(("OK  " if r["ok"] else "MISS"), r["symbol"], r["expect"], r["found"] or "", "| machine fills near:", r["near"])
    print(f"{hits}/{len(rows)}")
