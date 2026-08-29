"""Turn the latest completed audited study into concise website conclusions."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path("research/backtest/output")
OUT = Path("public/decision-summary.json")


def _metric(block):
    return {
        "samples": block["samples"],
        "win_rate": block["win_rate_pct"],
        "profit_factor": block["profit_factor"],
        "expectancy_pct": block["expectancy_pct"],
        "median_return_pct": block["median_pct"],
        "net_50bps_expectancy_pct": block["cost_sensitivity"]["50"]["expectancy_pct"],
    }


def _score_metric(block):
    return {
        "samples": block["samples"],
        "win_rate": block["win_rate_pct"],
        "profit_factor": block["profit_factor"],
        "expectancy_pct": block["expectancy_pct"],
        "median_return_pct": block["median_pct"],
    }


def run(out=OUT):
    report = json.loads((ROOT / "score-timeframe-attribution-v2.json").read_text())
    primary = report["primary_deduplicated"]
    baselines = {
        period: _metric(values["20"])
        for period, values in primary["baseline_fixed_horizon"].items()
    }
    forward_quintiles = primary["score_monotonicity"]["current"]["forward_2026"]["daily_midrank_quintiles"]
    low_score = _score_metric(forward_quintiles["1"]["20"])
    high_score = _score_metric(forward_quintiles["5"]["20"])
    payload = {
        "version": "production-evidence-v3.0.0",
        "generated_at": report["generated_at"],
        "source_experiment": report["experiment_id"],
        "production_status": "latest_research_synced_production_unchanged",
        "plain_summary": "最新完整审计已同步：共同门票的20日原始持有在开发期、2025和2026均为正，但分数越高并没有带来更高胜率或收益；31个附加因子和3个冻结组合都没有达到升级标准，因此不提高任何正式因子权重。",
        "coverage": {
            "start": report["coverage"]["start"],
            "end": report["coverage"]["end"],
            "audited_events": report["coverage"]["all_events"],
            "primary_events": report["coverage"]["primary_120_session_deduplicated_events"],
            "development": "2001—2024",
            "validation": "2025",
            "forward": "2026",
        },
        "counts": {
            "validated_add_on_factors": 0,
            "studied_add_on_factors": 31,
            "validated_pairs": 0,
            "studied_pairs": 3,
        },
        "usable": [{
            "name": "长期趋势＋完整日线MACD刚金叉",
            "role": "共同门票",
            "verdict": "继续使用",
            "metrics": baselines["forward_2026"],
            "periods": baselines,
            "note": "20日原始持有在开发 / 2025 / 2026三段胜率为54.39% / 50.98% / 54.29%，PF为1.228 / 1.356 / 1.513。它说明共同事件池值得继续研究，不等于实盘组合收益。",
        }],
        "watch": [
            {
                "name": "相对放量与60日回撤",
                "role": "高收益尾部标签",
                "verdict": "只观察",
                "note": "两项在三段高收益前10%样本中的出现率均高于基础率，但胜率和稳健平均收益没有一致改善，不能加分。",
            },
            {
                "name": "完整周线／月线MACD金叉",
                "role": "高周期研究",
                "verdict": "继续积累",
                "note": "完整周线20日样本只有65 / 10 / 8；月线长窗的2026成熟样本也不足且相对增量反向，不能作为买入门槛。",
            },
        ],
        "avoid": [
            {
                "name": "把高分解释成更高胜率",
                "verdict": "不成立",
                "metrics": high_score,
                "note": f'2026最高分组20日胜率{high_score["win_rate"]:.2f}%、PF {high_score["profit_factor"]:.3f}，反而低于最低分组的{low_score["win_rate"]:.2f}%和PF {low_score["profit_factor"]:.3f}；开发期和2025也不单调。',
            },
            {
                "name": "提高任一附加因子权重",
                "verdict": "暂不允许",
                "note": "31个附加因子中23个跨时期不稳定、8个样本不足，验证通过数为0。当前5个B级项若仍用于影子同分排序，也不能当作已验证买入依据。",
            },
            {
                "name": "直接采用两因子组合",
                "verdict": "样本不足",
                "note": "3个预先冻结组合都没有同时超过总体基线和两个组成单因子，不能进入生产。",
            },
        ],
        "method_note": "口径：120交易日内每只股票只保留首个事件；20日为单因子主窗口；开发期、2025独立验证和2026前向分开；20/50bps成本、1%去极值、BH多重比较均已检查。行业与大盘保持独立分层。",
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
