# Sage Vista

### 从市场噪音中，筛出有据可查的交易形态。

Sage Vista 是一个量化交易研究平台：扫描美股，筛选值得研究的机会，解释背后的依据，并持续追踪后续表现。

**[在线演示](https://sage-vista-parallel.gizmo-allied-0s.workers.dev) · [English](./README.md) · [项目文档](./docs/SAGE_VISTA_RULEBOOK_ZH.md)**

<!-- 截图 1：英文版多因子机会／排行榜（首屏）。
     预留路径：docs/assets/product/opportunity-ranking.en.png
     英文界面就绪后再添加图片。 -->

> **扫描 → 排序 → 解释 → 检验 → 改进**

## 研究概览

| 已审计历史事件 | 已登记因子 | 已登记实验 | 2026 年 20 日样本 |
|---:|---:|---:|---:|
| **62,000+** | **39** | **41** | **1,166** |

**已归档的 2026 年基线 · 持有 20 个交易日**

**胜率 54.3% · 盈利因子 1.51 · 成本前单事件平均收益 +2.10%**

以日线 MACD 金叉为事件，下一交易日复权开盘进入；同一股票在 120 个交易日内去重。研究截至 **2026 年 8 月 28 日**。计入 0.50% 的成本假设后，单事件平均收益为 **+1.60%**。

这些是历史事件研究结果，不是实盘或模拟组合收益，也不证明当前排行榜能预测收益。该研究中，高分并未持续对应更好的表现；历史退市股票覆盖仍不完整。

[研究方法与限制](./research/preregistrations/score-timeframe-attribution-v2.md) · [结果数据](./research/backtest/output/score-timeframe-attribution-v2.json)。因子数来自[注册表 v0.10.0](./public/factor-registry.json)；实验数来自 [2026 年 9 月 13 日目录](./research/generated/experiment-catalog.json)，包含尚未完成的实验。

## Sage Vista 能做什么

- **发现机会** — 从广泛的股票池中筛出值得深入研究的候选。
- **解释依据** — 查看价格结构、跨周期信号与支持因子。
- **补充背景** — 结合大盘、行业与风险环境判断形态。
- **持续验证** — 回测想法、追踪信号，保留成功与失败记录。

## 如何运作

**市场数据 → 初筛 → 形态与因子分析 → 大盘／行业背景 → 排序 → 追踪 → 验证**

分数是模型内证据的汇总，不代表盈利概率，也不保证收益。

## 产品一览

### 形态与证据

<!-- 截图 2：英文版形态／证据详情。
     预留路径：docs/assets/product/pattern-evidence.en.png -->

结合价格结构与月、周、日信号，理解一个机会为什么入选。

### 大盘与行业背景

<!-- 截图 3：英文版大盘／行业背景。
     预留路径：docs/assets/product/market-sector-context.en.png -->

查看整体环境是否支持当前形态，并将个股证据与市场背景分开呈现。

### 研究与验证

<!-- 截图 4：英文版研究／回测页面。
     预留路径：docs/assets/product/research-validation.en.png -->

查看历史检验与信号追踪，包括失败的想法和仍需更多证据的结果。

## 未来方向

Sage Vista 从选股工具起步，正逐步向更完整的交易系统发展：

**研究 → 决策 → 交易计划 → 模拟执行 → 风险管理 → 表现分析**

当前重点是研究、检验与人工决策支持，尚不提供实盘自动下单。

## 技术与本地开发

`Python` · `TypeScript` · `React` · `Cloudflare`

使用 **Node.js 22.13.0 或更新版本**在本地启动网页：

```bash
npm install
npm run dev
```

进一步了解[产品与方法](./docs/SAGE_VISTA_RULEBOOK_ZH.md)、[系统架构](./docs/SYSTEM_ARCHITECTURE_ZH.md)、[研究记录](./research/README.md)和[已记录的项目状态](./docs/CURRENT_STATUS_ZH.md)。详细文档和当前演示主要为中文；英文界面截图将在就绪后补充。

贡献者与智能体工作流程：[AGENTS.md](./AGENTS.md) · [执行规范](./docs/rules/01_GOVERNANCE.md)。
