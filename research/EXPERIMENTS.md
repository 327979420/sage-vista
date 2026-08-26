# Sage Vista Research Experiment Registry

本文件按完成顺序永久追加研究实验。结论为研究诊断，不自动修改 production。

## 1. Tracker Backtest V1 — Signal Validation

- **Purpose:** 将当前 Tracker point-in-time 重放到历史，检查 Long 信号、排名和趋势过滤。
- **Hypothesis:** Tracker 高排名/高分信号具有更好的后续表现，长期趋势过滤能够改善结果。
- **Dataset:** 2010-01-05—2026-06-24；378只 survivorship-aware 样本（含111只已知退市）；11,896条历史 Top 10 信号。
- **Benchmark:** 下一交易日复权 Open；1/3/5/10/20/40日 forward return；独立 strict trend control。
- **Key Results:** 20日胜率51.34%、PF 1.085；严格趋势胜率52.95%、PF 1.122。Tracker Rank 不单调，Multi-Factor Score 总体呈正梯度。
- **Conclusion:** 有薄弱 edge，但 Ranking 未验证；历史 universe 和重叠信号限制仍明显。
- **Commit SHA:** `6f8f8a2`

## 2. Stop Loss / Risk-Reward V2 — Risk Management

- **Purpose:** 固定 V1 信号与 Entry，比较六种 Stop 和1R/1.5R/2R/3R。
- **Hypothesis:** 更宽 Stop 可以减少正常波动洗出，并改善风险收益结构。
- **Dataset:** 冻结的11,896条 V1 历史信号；40-bar 路径；同 K 线 Stop-first。
- **Benchmark:** Confirmed/严格趋势分组；Support −1/−2/−3/−5%，Support −0.5/−1 ATR。
- **Key Results:** Support −5% + 2R 全样本 PF 1.102、Expectancy +0.489%；严格趋势 PF 1.159、Expectancy +0.694%。
- **Conclusion:** 宽 Stop 减少 Stop-out，但扩大风险与持有时间；没有自动选择参数。
- **Commit SHA:** `8a9a248`

## 3. Market Regime V1 — Market Context

- **Purpose:** 验证 SPY/QQQ 趋势、MACD 动能与 Breadth 能否改善固定 Long benchmark。
- **Hypothesis:** Risk-On 应优于 Neutral/Risk-Off，并改善 PF、Expectancy 和 Drawdown。
- **Dataset:** Point-in-time SPY/QQQ 与378只历史 universe；2010–2026固定 benchmark 信号。
- **Benchmark:** Confirmed + strict trend + next Open + Support −5% + 2R。
- **Key Results:** Risk-On PF 1.141、Expectancy +0.641%；全样本 PF 1.178、+0.801%。只做 Risk-On 减少31.45%样本但没有改善。
- **Conclusion:** 简单 Regime V1 未验证，且 Risk-Off 分期方向不一致；不进入 production。
- **Commit SHA:** `4996c03`

## 4. Factor Attribution V1 — Factor Research

- **Purpose:** 逐项比较固定 benchmark 中“有因子”与“无因子”的表现，解释 Rank 与 Score 分歧。
- **Hypothesis:** 部分现有因子在开发、验证和前向三段均稳定正贡献。
- **Dataset:** 2,817条 Confirmed + strict trend benchmark 交易；2010–2026。
- **Benchmark:** Next Open + Support −5% + 2R。
- **Key Results:** 没有样本充足的稳定正贡献因子；看涨吞没方向为正但样本不足；底部放量和突破回踩可能拖累。Rank 1–3 的层级分高但多因子均分更低。
- **Conclusion:** Tracker Rank 与 Multi-Factor Score 衡量不同质量；不调整权重。
- **Commit SHA:** `332cc00`

## 5. Ranking Research V1 — Ranking Ability

- **Purpose:** 在同一完整候选池比较 MACD、Multi-Factor、固定 Hybrid、固定 Random 和 No Ranking。
- **Hypothesis:** 有效 Ranking 应形成 Top 1–3 > 4–6 > 7–10，并稳定打败 Random/No Ranking。
- **Dataset:** 2010–2026；1,647个候选日、3,019条固定 benchmark 候选；完整候选账本。
- **Benchmark:** Confirmed + strict trend + next Open + Support −5% + 2R。
- **Key Results:** A/C 表面单调，但 Random 也单调；B 不单调。只有5天同时拥有至少10个候选，公平三档样本不足。No Ranking PF 1.196、Expectancy +0.875%。
- **Conclusion:** 没有 Ranking 被可靠验证；MACD 更适合候选发现，决定优先级仍需更多独立和更宽候选池样本。
- **Commit SHA:** `c5457c3`
