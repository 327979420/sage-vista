"""Publish the audited factor library as an actionable four-quadrant contract."""
from __future__ import annotations

import json
from pathlib import Path


SOURCE = Path("research/backtest/output/score-timeframe-attribution-v2.json")
REGISTRY = Path("public/factor-registry.json")
OUT = Path("public/factor-effectiveness.json")

PERIODS = ("development", "validation_2025", "forward_2026")
COMMON_GATES = {"qualification.long_trend", "macd.daily_bull_cross"}
SHADOW_TIEBREAKS = {
    "macd.weekly_histogram_improving",
    "structure.trendline_three_push",
    "volume.bottom_expansion",
    "structure.bottom_bullish_engulfing",
    "structure.support_bullish_engulfing",
}
TAIL_TAGS = {"qualification.pullback_60d", "volume.relative_expansion"}
RETIRE_CANDIDATES = {
    "support.fibonacci_half",
    "structure.double_bottom",
    "structure.higher_low",
    "structure.weekly_bullish_engulfing",
    "structure.weekly_double_bullish_engulfing",
    "structure.bottom_doji",
    "support.close_congestion",
    "support.volume_profile_proxy",
}

QUADRANTS = {
    "in_use": {
        "order": 1,
        "label_zh": "正在使用",
        "short_zh": "系统当前会用到",
        "description_zh": "共同门票直接决定是否入池；影子项只在基线相同的候选间作实验排序。在用不等于已经验证有效。",
        "action_zh": "保留当前角色，继续前向对照，不提高正式权重。",
    },
    "watch": {
        "order": 2,
        "label_zh": "候选观察",
        "short_zh": "有线索，但证据未成熟",
        "description_zh": "包括样本不足、尚未完成可比归因，以及只在高收益尾部出现较多的标签。",
        "action_zh": "继续记录，正式权重保持为0。",
    },
    "paused": {
        "order": 3,
        "label_zh": "暂停加权",
        "short_zh": "没有稳定收益增量",
        "description_zh": "开发期、2025验证期和2026前向期方向不一致，不能作为买入加分。",
        "action_zh": "检测和审计继续保留，当前不参与正式或影子加权。",
    },
    "retire": {
        "order": 4,
        "label_zh": "准备弃用",
        "short_zh": "旧结论已拒绝或证据重复",
        "description_zh": "历史证据永久保留；这里只表示从未来评分候选和主研究视图中退休，不删除旧事件。",
        "action_zh": "保持0权重；完成兼容迁移后再决定是否停掉日常检测。",
    },
}

FAMILIES = {
    "qualification": ("基础资格", "#4F6BED"),
    "trend": ("趋势", "#0F766E"),
    "macd": ("MACD", "#D97706"),
    "support": ("支撑", "#2F855A"),
    "price_structure": ("价格结构", "#7C3AED"),
    "rsi": ("RSI", "#C2416C"),
    "volume": ("量能", "#0284C7"),
    "risk": ("风险／供给", "#B45353"),
}

TIMEFRAMES = {
    "daily": "日线",
    "weekly_completed": "完整周线",
    "monthly_completed": "完整月线",
}

VERDICTS = {
    "common_gate": "共同门票，不作附加因子证明",
    "unstable": "跨时期不稳定",
    "sample_insufficient": "样本不足",
    "not_in_v2": "尚未进入本轮可比归因",
}


def _period_metric(item: dict | None, period: str) -> dict | None:
    if not item:
        return None
    block = item["periods"][period]["20"]
    hit, delta, enrichment = block["with"], block["delta"], block["enrichment"]
    return {
        "samples": hit["samples"],
        "win_rate_pct": hit["win_rate_pct"],
        "profit_factor": hit["profit_factor"],
        "expectancy_pct": hit["expectancy_pct"],
        "win_delta_pct": delta["win_rate_pct"],
        "median_delta_pct": delta["median_pct"],
        "trimmed_mean_delta_pct": delta["trimmed_mean_pct"],
        "expectancy_delta_pct": delta["expectancy_pct"],
        "top_decile_enrichment_ratio": enrichment["top_decile_enrichment_ratio"],
    }


def _quadrant(factor_id: str, verdict: str) -> str:
    if factor_id in COMMON_GATES or factor_id in SHADOW_TIEBREAKS:
        return "in_use"
    if factor_id in RETIRE_CANDIDATES:
        return "retire"
    if factor_id in TAIL_TAGS or verdict in {"sample_insufficient", "not_in_v2"}:
        return "watch"
    return "paused"


def _production_role(factor_id: str) -> tuple[str, str]:
    if factor_id == "macd.daily_bull_cross":
        return "event_gate", "事件门票"
    if factor_id == "qualification.long_trend":
        return "eligibility_gate", "候选资格"
    if factor_id in SHADOW_TIEBREAKS:
        return "shadow_tiebreak", "影子同分参考"
    if factor_id in TAIL_TAGS:
        return "descriptive_tail_tag", "高收益尾部标签"
    return "zero_weight", "当前0权重"


def _action(factor_id: str, quadrant: str, verdict: str) -> tuple[str, str]:
    if factor_id == "macd.daily_bull_cross":
        return "继续作为唯一事件门票", "所有样本都先满足它，因此不能把它的出现次数当成附加因子优势。"
    if factor_id == "qualification.long_trend":
        return "继续作为共同候选资格", "与日线MACD刚金叉共同构成基线，不代表高分更有效。"
    if factor_id in SHADOW_TIEBREAKS:
        return "维持影子同分参考，正式分仍为0", "最新V2判定跨时期不稳定；当前虽在影子排序中使用，但不能单独作为买入依据。"
    if factor_id in TAIL_TAGS:
        return "只作高收益尾部观察标签", "三段高收益前10%中的出现率都高于基础率，但胜率和稳健平均收益没有稳定改善。"
    if quadrant == "retire":
        return "准备从未来评分候选中退休", "旧登记已拒绝或证据重复，最新V2仍未证明稳定增量；历史命中与失败实验继续保留。"
    if verdict == "sample_insufficient":
        return "继续积累样本，不加权", "至少一个独立阶段未达到冻结样本门槛，不能因局部好看升级。"
    if verdict == "not_in_v2":
        return "完成机器定义和可比归因后再决定", "本轮完整事件池没有可比结果，当前只保留登记与0权重。"
    return "暂停加权，只保留位置或审计证据", "开发期、2025验证期和2026前向期的增量方向不一致。"


def run(source=SOURCE, registry=REGISTRY, out=OUT):
    report = json.loads(Path(source).read_text())
    registered = json.loads(Path(registry).read_text())
    primary = report["primary_deduplicated"]
    studied = {row["factor_id"]: row for row in primary["single_factors"]}
    factors = []
    for position, factor in enumerate(registered["factors"]):
        factor_id = factor["id"]
        study = studied.get(factor_id)
        verdict = "common_gate" if factor_id in COMMON_GATES else study["verdict"] if study else "not_in_v2"
        quadrant = _quadrant(factor_id, verdict)
        role, role_zh = _production_role(factor_id)
        action, note = _action(factor_id, quadrant, verdict)
        family_name, family_color = FAMILIES[factor["evidence_family"]]
        factors.append({
            "factor_id": factor_id,
            "name_zh": factor["name_zh"],
            "family": factor["evidence_family"],
            "family_zh": family_name,
            "family_color": family_color,
            "timeframe": factor["timeframe"],
            "timeframe_zh": TIMEFRAMES.get(factor["timeframe"], factor["timeframe"]),
            "quadrant": quadrant,
            "quadrant_zh": QUADRANTS[quadrant]["label_zh"],
            "production_role": role,
            "production_role_zh": role_zh,
            "current_use": role in {"event_gate", "eligibility_gate", "shadow_tiebreak"},
            "official_weight": factor.get("weight", 0),
            "shadow_weight": factor.get("experimental_weight", 0),
            "latest_verdict": verdict,
            "latest_verdict_zh": VERDICTS[verdict],
            "action": action,
            "evidence_note_zh": note,
            "periods_20d": {period: _period_metric(study, period) for period in PERIODS},
            "registry_position": position,
        })
    factors.sort(key=lambda row: (QUADRANTS[row["quadrant"]]["order"], row["registry_position"]))
    for row in factors:
        row.pop("registry_position")

    baseline = primary["baseline_fixed_horizon"]
    baseline_20d = {
        period: {
            "samples": values["20"]["samples"],
            "win_rate_pct": values["20"]["win_rate_pct"],
            "median_pct": values["20"]["median_pct"],
            "profit_factor": values["20"]["profit_factor"],
            "expectancy_pct": values["20"]["expectancy_pct"],
            "net_50bps_expectancy_pct": values["20"]["cost_sensitivity"]["50"]["expectancy_pct"],
        }
        for period, values in baseline.items()
    }
    counts = {key: sum(row["quadrant"] == key for row in factors) for key in QUADRANTS}
    verdict_counts = {
        key: sum(row["verdict"] == key for row in primary["single_factors"])
        for key in ("unstable", "sample_insufficient")
    }
    weekly = studied["macd.weekly_bull_cross"]
    payload = {
        "version": "factor-effectiveness-v3.0.0",
        "generated_at": report["generated_at"],
        "source_experiment": report["experiment_id"],
        "production_scoring_changed": False,
        "coverage": {
            "period": f'{report["coverage"]["start"]}—{report["coverage"]["end"]}',
            "development": "2001—2024",
            "validation": 2025,
            "forward": 2026,
            "source_signals_end": report["coverage"]["end"],
            "source_candidates": 63817,
            "audited_events": report["coverage"]["all_events"],
            "primary_events": report["coverage"]["primary_120_session_deduplicated_events"],
            "factors": len(factors),
        },
        "headline": {
            "common_gate": "长期趋势＋完整日线MACD刚金叉的20日原始持有在三段均为正。",
            "score": "当前分、周期等权和V3都没有形成跨期单调性；高分不能解释成更高胜率。",
            "add_on": f'31个附加研究因子中0个验证通过：{verdict_counts["unstable"]}个不稳定、{verdict_counts["sample_insufficient"]}个样本不足。',
            "pairs": "3个冻结两因子组合均样本不足，没有组合可升级。",
        },
        "quadrant_order": list(QUADRANTS),
        "quadrants": QUADRANTS,
        "quadrant_counts": counts,
        "family_legend": [
            {"family": key, "label_zh": value[0], "color": value[1]}
            for key, value in FAMILIES.items()
        ],
        "baseline_20d": baseline_20d,
        "factors": factors,
        "research_only": [{
            "factor_id": "macd.weekly_bull_cross",
            "name_zh": "完整周线MACD刚金叉",
            "verdict": weekly["verdict"],
            "summary_zh": "20日主样本仅为开发65 / 2025年10 / 2026年8，样本不足且2026方向偏弱；不进入生产注册表。",
        }],
        "warning": "四象限是研究治理与当前用途说明，不是买入承诺。行业和大盘未混入技术因子结论；原始固定持有也不是资金受限组合或止损退出结果。",
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
