"""How much price history a long dataset gives each year (an engineering check; no returns are computed).

The monthly-led buy system (docs/BUY_SYSTEM_ZH.md) reads monthly EMA200, which
needs about 200 months of bars. This check counts, for every year, how many
stocks were trading and how many had 50, 120 and 200 months of history before
the year began, and how much history each reviewed case had on its date.
"""
from __future__ import annotations

MONTHS = (50, 120, 200)


def months_before(first_date, day):
    """Whole calendar months of bars before `day`'s month, given the first bar's date."""
    fy, fm = int(first_date[:4]), int(first_date[5:7])
    y, m = int(day[:4]), int(day[5:7])
    return max(0, (y - fy) * 12 + (m - fm))


def run(spec, data, dataset_entry):
    prices = data["prices"]
    first_years, last = {}, {}
    for symbol, series in prices.items():
        first_years[symbol], last[symbol] = series["date"][0], series["date"][-1]
    years = []
    for year in range(spec["years"][0], spec["years"][1] + 1):
        start, end = f"{year}-01-01", f"{year}-12-31"
        trading = [s for s in prices if first_years[s] <= end and last[s] >= start]
        row = {"year": year, "trading": len(trading)}
        for months in MONTHS:
            row[f"with_{months}_months"] = sum(1 for s in trading if months_before(first_years[s], start) >= months)
        years.append(row)
    cases = []
    for case in spec.get("cases", []):
        series = prices.get(case["symbol"])
        months = months_before(series["date"][0], case["date"]) if series else None
        cases.append({"symbol": case["symbol"], "date": case["date"], "first_bar": series["date"][0] if series else None,
                      "months_before": months, "monthly_ema200_ready": months is not None and months >= 200})
    requested = len(prices) + len(data.get("missing_symbols", []))
    missing_share = len(data.get("missing_symbols", [])) / requested if requested else 1.0
    passed = missing_share <= spec["criteria"]["max_missing_share"]
    return {"spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"], "kind": "coverage",
            "dataset": dataset_entry, "champion": None, "passed": passed,
            "symbols": {"requested": requested, "built": len(prices), "missing": data.get("missing_symbols", []), "missing_share": round(missing_share, 4)},
            "earliest_first_bar": min(first_years.values()) if first_years else None, "years": years, "cases": cases}


def render(result):
    s = result["symbols"]
    lines = [f"# {result['spec_id']}", "",
             f"Engineering check written by the research lab on {result.get('completed_at', '—')[:10]}; no returns are computed. "
             "Every number comes from `result.json` in this folder.", "",
             "## The question", "", result["question"], "",
             "## The short answer", "",
             f"- Built {s['built']} of {s['requested']} symbols ({s['missing_share'] * 100:.1f}% missing); earliest bar {result['earliest_first_bar']}. "
             f"Check passed: **{'yes' if result['passed'] else 'no'}**.", "",
             "## History available at the start of each year", "",
             "| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |", "|---|---|---|---|---|"]
    for r in result["years"]:
        lines.append(f"| {r['year']} | {r['trading']} | {r['with_50_months']} | {r['with_120_months']} | {r['with_200_months']} |")
    if result["cases"]:
        lines += ["", "## Reviewed cases", "", "| Case | Date | First bar | Months before | Monthly EMA200 ready |", "|---|---|---|---|---|"]
        for c in result["cases"]:
            lines.append(f"| {c['symbol']} | {c['date']} | {c['first_bar'] or 'no data'} | {c['months_before'] if c['months_before'] is not None else '—'} | "
                         f"{'yes' if c['monthly_ema200_ready'] else 'no'} |")
    if s["missing"]:
        lines += ["", "## Missing symbols", "", ", ".join(s["missing"])]
    return "\n".join(lines) + "\n"
