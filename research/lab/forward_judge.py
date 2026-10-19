"""Task036 net-R scorecard. Offline, read-only replay of frozen forward trades.

CLI replays the forward job's local dataset and bulk caches; run immediately
following triangle_forward. It never downloads prices or changes frozen records.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as stats

from research.lab import buysystem as BS, datasets, selection, triangle15 as N
from research.lab import triangle_forward as F

DONE = {"win", "loss", "time"}
COST = 0.001


def mean(values):
    return stats.fmean(values) if values else None


def net_r(e, x, stop):
    return (x * (1 - COST) - e * (1 + COST)) / (e - stop)


def detail(g, stop):
    return {**g, "e": g.get("entry"), "x": g.get("exit"), "stop": stop,
            "net_R": net_r(g["entry"], g["exit"], stop)
            if g.get("status") in DONE and g.get("R") is not None else None}


def twins(PX, rec, pool, m):
    """Keep draw order and all skipped/uncompleted draws for audit."""
    seed = int(hashlib.sha256(rec["id"].encode()).hexdigest()[:8], 16)
    rows = []
    for sym in random.Random(seed).sample(pool, min(30, len(pool))):
        row = {"symbol": sym, "status": "skipped", "e": None, "x": None, "stop": None, "net_R": None}
        rows.append(row)
        q = PX[sym]
        i0 = bisect.bisect_left(q["date"], rec["signal_day"])
        if i0 >= len(q["date"]) or q["date"][i0] != rec["signal_day"]:
            row["why"] = "信号日无价格"
            continue
        Q = BS.periods(q, "week")
        j = BS.completed(Q, i0, len(q["close"]))
        if j < 20 or not Q["atr"][j]:
            row["why"] = "周线或ATR不足"
            continue
        L = q["close"][i0] * 0.98
        st = L - m * Q["atr"][j]
        row["stop"] = st
        if st <= 0 or (L - st) / L > 0.4:
            row["why"] = "止损不合条件"
            continue
        row.update(detail(N.trade(q, i0, L, st, L + 3.0 * (L - st), hold=130), st))
    return rows


def recompute(PX, records, outcomes, config):
    """One dataset's PX, exactly as extended by the forward run. No mutation."""
    if config.get("random_twins", 30) != 30:
        raise ValueError("任务036要求30只孪生")
    by = {o["id"]: o for o in outcomes}
    rules = {**N.POOL, "exclude": selection.impossible_jumps(PX) | N.FUNDS}
    pools, rows = {}, []
    for rec in records:
        frozen = by.get(rec["id"], {}).get("r19", {})
        row = {"id": rec["id"], "signal_day": rec["signal_day"], "week": rec["week"],
               "eligible": bool(rec["plan"]["go"] and rec.get("market", {}).get("ok")),
               "frozen": frozen, "completed": frozen.get("status") in DONE,
               "trade": None, "exit_date": None, "twins": [], "gross_twin_mean": None, "net_twin_mean": None,
               "d": None, "gross_difference": None, "scored": False,
               "check": "无冻结核对" if "random_R" not in frozen else "一致"}
        rows.append(row)
        if not rec["plan"]["go"]:
            continue
        s = PX.get(rec["symbol"])
        if not s or rec["signal_day"] not in s["date"]:
            row["reason"] = "缺价格"
            continue
        p = rec["plan"]
        g = N.trade(s, s["date"].index(rec["signal_day"]), p["level"], p["stop"],
                    p["level"] + 3 * (p["level"] - p["stop"]), hold=130)
        row["trade"] = detail(g, p["stop"])
        if "exit_day" in g:
            row["exit_date"] = s["date"][g["exit_day"]]
        W = BS.periods(s, "week")
        if rec["week"] not in W["date"] or not W["atr"][W["date"].index(rec["week"])]:
            row["reason"] = "信号周ATR缺失"
        else:
            m = (p["level"] - p["stop"]) / W["atr"][W["date"].index(rec["week"])]
            day = rec["signal_day"]
            if day not in pools:
                pools[day] = selection.eligible_pool(PX, day, rules)
            row["twins"] = twins(PX, rec, [x for x in pools[day] if x != rec["symbol"]], m)
        done = [t for t in row["twins"] if t["status"] in DONE and t.get("R") is not None]
        row["gross_twin_mean"] = mean([t["R"] for t in done])
        row["net_twin_mean"] = mean([t["net_R"] for t in done])
        def rounded(v):
            return round(v, 4) if v is not None else None
        if row["completed"] and (g["status"] != frozen["status"] or
                rounded(g.get("R")) != rounded(frozen.get("R")) or
                ("random_R" in frozen and rounded(row["gross_twin_mean"]) != rounded(frozen["random_R"]))):
            row["check"] = "对照不一致"
        if g.get("R") is not None and done:
            row["gross_difference"] = g["R"] - row["gross_twin_mean"]
        row["scored"] = (row["eligible"] and row["completed"] and row["trade"]["net_R"] is not None
                         and bool(done) and row["check"] != "对照不一致")
        if row["scored"]:
            row["d"] = row["trade"]["net_R"] - row["net_twin_mean"]
    return rows


def paper_metrics(path):
    if path is None or not Path(path).exists():
        return {"status": "未提供"}
    rows = json.loads(Path(path).read_text())
    if not isinstance(rows, list) or len(rows) < 2:
        return {"status": "数据不足"}
    dates = [r["date"] for r in rows]
    if dates != sorted(set(dates)):
        raise ValueError("模拟账户日期须严格递增且无重复")
    out = {"status": "已提供", "from": dates[0], "to": dates[-1],
           "convention": "共同日期；日简单收益；样本标准差；252日年化；无风险利率0；最大峰谷回撤"}
    for key in ("core", "satellite", "total", "spy"):
        v = [r[key] for r in rows]
        if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in v):
            raise ValueError(f"{key}净值须为正有限数，不补缺失值")
        returns = [b / a - 1 for a, b in zip(v, v[1:])]
        sd = stats.stdev(returns) if len(returns) > 1 else 0
        peak, dd = v[0], 0
        for x in v:
            peak = max(peak, x)
            dd = max(dd, 1 - x / peak)
        out[key] = {"return": v[-1] / v[0] - 1, "drawdown": dd,
                    "sharpe": mean(returns) / sd * math.sqrt(252) if sd else None}
    return out


def paired_stats(scored):
    ds = [r["d"] for r in scored]
    avg = mean(ds)
    sd = stats.stdev(ds) if len(ds) > 1 else None
    return avg, avg / (sd / math.sqrt(len(ds))) if sd else None


def judge_checkpoint(done, paper):
    """Judge exactly this completed-trade prefix, including unscorable rows."""
    k = len(done)
    scored = [r for r in done if r["scored"]]
    avg, t = paired_stats(scored)
    pause = (k - len(scored)) / k > 0.1
    alarm1 = bool(not pause and t is not None and avg < 0 and t <= -2)
    satellite, spy = paper.get("satellite", {}), paper.get("spy", {})
    effective = bool(k >= 100 and not pause and t is not None and t >= 2
                     and satellite.get("sharpe") is not None and spy.get("sharpe") is not None
                     and satellite["sharpe"] >= spy["sharpe"])
    verdict = ("暂停判断（对照不足）" if pause else "失效警报1" if alarm1 else
               "证明有效" if effective else "继续记录，未证明")
    return {"k": k, "scored": len(scored), "unscorable": k-len(scored),
            "mean_d": avg, "t": t, "alarm1": alarm1, "verdict": verdict}


def score(rows, paper=None):
    paper = paper or {"status": "未提供"}
    done = [r for r in rows if r["eligible"] and r["completed"]]
    if any(not r.get("exit_date") for r in done):
        raise ValueError("已结束交易缺重算退出日期，无法确定检查点顺序")
    done = sorted(done, key=lambda r: (r["exit_date"], r["id"]))
    scored = [r for r in done if r["scored"]]
    n = len(done)
    reached = [k for k in (30, 60) if k <= n] + list(range(100, n + 1, 100))
    checkpoints = [judge_checkpoint(done[:k], paper) for k in reached]
    latest = checkpoints[-1] if checkpoints else None
    checkpoint = bool(checkpoints)
    nxt = next((x for x in (30, 60, 100) if x > n), (n // 100 + 1) * 100)
    avg, t = paired_stats(scored)
    # Any reached checkpoint that fired counts: a run that jumps past several checkpoints must not hide an earlier alarm.
    alarm1 = any(c["alarm1"] for c in checkpoints)
    satellite = paper.get("satellite", {})
    alarm2 = satellite["drawdown"] > .25 if "drawdown" in satellite else "未提供"
    verdict = latest["verdict"] if latest else "继续记录，未证明"
    rs = [r["trade"]["net_R"] for r in scored]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r < 0]
    return {"verdict": verdict, "completed": n, "scored": len(scored), "unscorable": n-len(scored),
            "mismatched": sum(r["check"] == "对照不一致" for r in done),
            "no_frozen_check": sum("random_R" not in r["frozen"] for r in done),
            "checkpoint": checkpoint, "checkpoints": checkpoints, "next_checkpoint": nxt, "to_go": nxt-n,
            "mean_d": avg, "t": t, "alarm1": alarm1, "alarm2": alarm2,
            "win_rate": len(wins)/len(rs) if rs else None,
            "payoff_ratio": mean(wins)/-mean(losses) if wins and losses else None,
            "profit_factor": sum(wins)/-sum(losses) if losses else None,
            "mean_net_R": mean(rs), "random_net_R": mean([r["net_twin_mean"] for r in scored]),
            "gross_check": mean([r["gross_difference"] for r in scored]),
            "paper": paper, "rows": rows}


def markdown(report):
    def show(x):
        return "不可计算" if x is None else str(round(x, 6)) if isinstance(x, float) else str(x)
    lines = [report["verdict"], "", "状态：已实现，尚不能正式计分；等待workflow批准及Claude核查。",
             f"已结束 {report['completed']} 笔；可计分 {report['scored']}；不可计分 {report['unscorable']}。",
             f"对照不一致 {report['mismatched']}；无冻结核对 {report['no_frozen_check']}。",
             f"下一检查点 {report['next_checkpoint']} 笔，还差 {report['to_go']} 笔。",
             "结论沿用最近已达到的检查点；检查点之间只记录。每年10月另作描述性年报。", "",
             "| 检查点k | 可计分 | 不可计分 | 净R差均值 | t | 结论 |",
             "|---|---|---|---|---|---|"]
    for cp in report["checkpoints"]:
        lines.append("| " + " | ".join(show(cp[k]) for k in
                     ("k", "scored", "unscorable", "mean_d", "t", "verdict")) + " |")
    lines += ["", "以下交易统计覆盖当前全部可计分交易；警报1沿用最近检查点。"]
    if report["alarm2"] is True:
        lines.append("失效警报2：由owner决定暂停新3W卫星仓。")
    for label, key in [("净R差均值", "mean_d"), ("t", "t"), ("警报1", "alarm1"), ("警报2", "alarm2"),
                       ("胜率", "win_rate"), ("盈亏比", "payoff_ratio"), ("profit factor", "profit_factor"),
                       ("平均净R", "mean_net_R"), ("随机孪生平均净R", "random_net_R"),
                       ("毛 R 差（未扣费，仅核对用）", "gross_check")]:
        value = report[key]
        if isinstance(value, bool):
            value = "触发" if value else "未触发"
        lines.append(f"- {label}：{show(value)}")
    lines += ["", "交易统计仅含可计分交易；不裁剪R。样本不足或零方差时t不可计算，不作显著性判断。",
              "账户：" + report["paper"]["status"]]
    for label, key in [("核心", "core"), ("卫星", "satellite"), ("合计", "total"), ("SPY", "spy")]:
        p = report["paper"].get(key, {})
        lines.append(f"- {label}：收益 {show(p.get('return'))}；最大回撤 {show(p.get('drawdown'))}；Sharpe {show(p.get('sharpe'))}")
    if "convention" in report["paper"]:
        lines.append(report["paper"]["convention"] + "；以上四项使用同一输入日期区间。")
    lines += ["", "限制：重复检查会累积误报；交易可能相关。账户输入必须覆盖同期且不含外部现金流，未提供时不判断有效。"]
    lines.append("限制：若本地缺少某个bulk缓存交易日，缺冻结孪生值（无冻结核对）的交易无法被复现闸门检出；正式计分必须在前向任务中运行。")
    return "\n".join(lines) + "\n"


def cached_prices(ds, config, as_of):
    """Replay only locally cached bulk sessions, capped at the frozen outcome date."""
    entry = datasets.manifest(ds)
    PX = datasets.load(F.ROOT / "work/lab" / entry["asset"], entry["sha256"])["prices"]
    days = sorted(p.name[:10] for p in F.BULK.glob("*.json.gz")
                  if config["calendar_from"] <= p.name[:10] <= as_of)
    def bars(day):
        return json.loads(gzip.decompress((F.BULK / f"{day}.json.gz").read_bytes()))
    F.extend(PX, days, bars)
    return PX


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", type=Path)
    parser.add_argument("--out", type=Path, default=F.ROOT / "work/forward-judge")
    args = parser.parse_args(argv)
    config = json.loads(F.CONFIG.read_text())
    frozen = json.loads((F.ROOT / F.FOLDER / "outcomes.json").read_text())
    records = F.load_records()
    rows = []
    for ds in config["datasets"]:
        recs = [r for r in records if r["dataset"] == ds]
        if recs:
            rows.extend(recompute(cached_prices(ds, config, frozen["computed_at"][:10]), recs, frozen["outcomes"], config))
    if len(rows) != len(records):
        raise ValueError("信号含未知数据集，拒绝漏计")
    report = score(rows, paper_metrics(args.paper))
    report["computed_at"] = frozen["computed_at"]
    report["price_source"] = "冻结数据集及同次前向运行的本地bulk缓存；无网络请求"
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (args.out / "latest.md").write_text(markdown(report))
    print(f"{report['verdict']}；已结束 {report['completed']} 笔；{args.out}")


if __name__ == "__main__":
    main()
