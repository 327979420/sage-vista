# Sage Vista 模块规则索引

最后更新：2026-08-29

## 使用方法

1. 新对话先读 `../NEXT_SESSION_HANDOFF_ZH.md` 和 `../CURRENT_STATUS_ZH.md`。
2. 从总手册的模块地图定位改动，并在 `../CHANGE_REQUESTS_ZH.md` 逐条记录用户意图。
3. 按`../CHANGE_WORKFLOW_ZH.md`提交架构设计包，状态置为`design_review`；用户明确批准前不得改业务代码。
4. 只完整阅读受影响的模块文件及其“联动条件”列出的文件。
5. 获批后先改规则与版本，再改代码和测试；每个实现包预计不超过20分钟。
6. 如果实际结果可能变化，再预登记实验。
7. 完成后把结论、测试、提交、生产链接和产物永久留档。

## 精准路由

| 需求示例 | 主文件 | 何时需要联动 |
|---|---|---|
| “月线吞没改几分” | `04_SCORING.md` | 若检测定义也变，再改 `03_FACTOR_MODEL.md` |
| “新增 K 线跟随” | `03_FACTOR_MODEL.md` | 若给分，再改 `04_SCORING.md`；若回测，再改 `08_*` |
| “MACD 不再作为触发器” | `02_DATA_AND_SCAN.md` | 必须联动 `08_*`，因为事件池要重建 |
| “行业成交量热点怎么算” | `06_INDUSTRY.md` | 若改变排行，再联动 `07_*` 和 `08_*` |
| “精选机会门槛” | `07_RANKING_AND_TRACKING.md` | 若分值公式变，再联动 `04_*` |
| “止损从 5% 改成 10%” | `09_RISK_AND_EXECUTION.md` | 必须联动 `08_*` 登记新实验 |
| “实验页怎么展示” | `10_UI_AND_OPERATIONS.md` | 不改变实验统计定义时无需改 `08_*` |
| “这套因子组合已经证明能用” | `11_VALIDATED_PLAYBOOK.md` | 必须引用已经完成的 `08_*` 实验 |
| “以后绝对不要碰这种交易” | `12_HARD_RULES.md` | 必须记录证据、适用范围和解除条件 |

`*` 是同目录中名称的缩写。模块版本独立递增；只有全局原则或模块边界改变时才升级总手册。

## 模块接手表

| 模块 | 主要实现入口 | 主要状态 / 产物 | 首要测试 |
|---|---|---|---|
| 01 治理 | `AGENTS.md`、`docs/*.md` | `CURRENT_STATUS_ZH.md`、`CHANGE_REQUESTS_ZH.md` | `test_rulebook_contract.py`、`test_project_status.py` |
| 02 数据扫描 | `daily_tracker_update.py`、`eodhd.py`、`factor_snapshot.py` | `update-status.json`、`daily-factor-snapshot.json` | `test_eodhd.py`、`test_factor_snapshot.py` |
| 03 因子模型 | `factor_registry.py`、`factor_detectors.py`；研究候选另见`research/factor_lab/` | `factor-registry.json`、`research/factor-candidates-v2.json` | `test_factor_snapshot.py`、`test_factor_scoring.py`、`test_factor_strategy_lab_v2.py` |
| 04 评分 | `factor_scoring.py`、`unified_v2_scan.py` | `unified-v2-rankings.json` | `test_factor_scoring.py`、`test_unified_v2_scan.py` |
| 05 大盘 | `market_etf_watch.py` | `market-etf-watch.json` | `test_market_etf_watch.py` |
| 06 行业 | `industry_radar.py`、`industry_membership.py` | `industry-radar.json` | `test_industry_radar.py` |
| 07 排行追踪 | `unified_v2_scan.py`、`opportunity_ledger.py`、`signal_history.py` | `unified-v2-rankings.json`、`opportunity-ledger.json`、`signal-history.json` | `test_opportunity_ledger.py`、`test_signal_history.py` |
| 08 回测实验 | `research/backtest/`、`experiment_catalog.py`、`backtest_progress.py` | `research/experiments.jsonl`、`backtest-state.json`、`research/generated/experiment-catalog.json` | `test_backtest_progress.py`、`test_experiment_catalog.py` |
| 09 风险执行 | `support_risk.py`、研究回测脚本 | 风险 / 退出实验产物 | `test_support_risk.py`、对应回测测试 |
| 10 UI 运维 | `app/`、`.github/workflows/`、`verify_live_deployment.py` | 生产网站、`production-state.json` | `test_ui_v2_contract.py`、`rendered-html.test.mjs` |
| 11 策略宝典 | 已验证实验引用 | `11_VALIDATED_PLAYBOOK.md` | 规则契约测试 |
| 12 交易红线 | 证据与禁区条目 | `12_HARD_RULES.md` | 规则契约测试 |
