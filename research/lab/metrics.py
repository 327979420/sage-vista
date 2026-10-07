"""Standard metrics and the pre-registered pass test for every lab experiment.

Every variant in every experiment is summarised the same way, so results from
different months and datasets stay directly comparable on the scoreboard.
Event-level results overlap and are not a capital-constrained portfolio.
"""
from __future__ import annotations

import math
import statistics


def summarise(trades):
    resolved = [t for t in trades if t.get("status") == "resolved"]
    out = {"events": len(trades), "resolved": len(resolved),
           "skipped": sum(t.get("status") == "skipped" for t in trades),
           "observing": sum(t.get("status") == "observing" for t in trades)}
    if not resolved:
        return out
    net = [t["net_return"] for t in resolved]
    rs = [t["r_multiple"] for t in resolved]
    gains, losses = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    sd_r = statistics.pstdev(rs) if len(rs) > 1 else 0.0
    mean_r = statistics.fmean(rs)
    reasons = [t["exit_reason"] for t in resolved]
    ordered = sorted(net)
    out.update(
        win_rate=round(sum(x > 0 for x in net) / len(net), 4),
        mean_return=round(statistics.fmean(net), 6),
        median_return=round(statistics.median(net), 6),
        p10_return=round(ordered[int(0.1 * (len(ordered) - 1))], 6),
        profit_factor=round(gains / losses, 4) if losses else None,
        expectancy_r=round(mean_r, 4),
        sd_r=round(sd_r, 4),
        # Van Tharp's System Quality Number with N capped at 100 trades.
        sqn=round(math.sqrt(min(len(rs), 100)) * mean_r / sd_r, 3) if sd_r else None,
        t_stat=round(math.sqrt(len(rs)) * mean_r / sd_r, 3) if sd_r else None,
        avg_hold=round(statistics.fmean(t["held"] for t in resolved), 2),
        stop_rate=round(sum(r.startswith("stop") for r in reasons) / len(reasons), 4),
        trail_rate=round(sum(r.startswith("trail") or r == "trend_exit" for r in reasons) / len(reasons), 4),
        target_rate=round(sum(r == "target" for r in reasons) / len(reasons), 4),
        time_rate=round(sum(r == "time" for r in reasons) / len(reasons), 4),
    )
    return out


def evaluate(overall, splits, neighbours, criteria):
    """Apply the frozen criteria; every check is reported, not only the verdict."""
    checks = {
        "expectancy_r": (overall.get("expectancy_r") or -9) >= criteria["min_expectancy_r"],
        "profit_factor": (overall.get("profit_factor") or 0) >= criteria["min_profit_factor"],
        "sqn": (overall.get("sqn") or -9) >= criteria["min_sqn"],
        "every_split_positive": all((s.get("mean_return") or -1) > 0 for s in splits.values() if s.get("resolved", 0) >= criteria["min_split_trades"]),
        "enough_trades": overall.get("resolved", 0) >= criteria["min_trades"],
        "neighbours_positive": all((n.get("expectancy_r") or -1) > 0 for n in neighbours),
    }
    return {"passed": all(checks.values()), "checks": checks}
